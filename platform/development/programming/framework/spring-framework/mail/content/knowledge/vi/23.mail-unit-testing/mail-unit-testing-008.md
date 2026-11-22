# Kiểm tra attachment, inline resource và Content-ID

## 1. Mục tiêu của kiểm thử đơn vị trong Spring Framework Mail

Khi một ứng dụng gửi email bằng **Spring Framework Mail**, một thông báo có thể chứa phần văn bản, HTML, ảnh nhúng vào nội dung và các tệp đính kèm. Việc gọi `JavaMailSender.send(...)` không tự chứng minh người nhận sẽ thấy đúng tệp hoặc đúng ảnh. Lỗi có thể xuất phát ngay từ bước **tạo `MimeMessage`**, trước khi SMTP server nhận email:

- PDF được thêm thành ảnh inline, hoặc ảnh logo bị đặt như một attachment.
- Header `Content-ID` không khớp giá trị `cid:...` trong HTML.
- Email chứa hai ảnh nhưng cả hai có cùng Content-ID nên tham chiếu không rõ ràng.
- Content-Type khai báo `image/png` nhưng nội dung resource là một tệp khác.
- Tên file attachment thiếu hoặc sai sau khi mã hóa MIME.
- Bản `text/plain` và `text/html` bị đặt không đúng quan hệ `multipart/alternative`.
- Resource chỉ đọc được một lần, khiến việc serialize MIME hoặc gửi lại thất bại.
- Trong test, mock xác nhận `send` đã được gọi nhưng không kiểm tra bên trong email đã tạo.

Vì thế, bài kiểm thử tốt phải kiểm tra **MIME message được tạo ra**, không chỉ số lần gọi phương thức. Trong chương *Kiểm thử đơn vị*, ta sẽ chủ yếu tạo mail **trong bộ nhớ**, sử dụng `MimeMessageHelper`, duyệt cây MIME, kiểm tra header và đọc lại dữ liệu nhị phân; không cần SMTP thật cho những kiểm tra này.

### Kết quả mong đợi

Sau khi thực hành, có thể kiểm tra được:

1. Nội dung HTML tham chiếu đúng ảnh bằng `cid:logo`.
2. Ảnh có `Content-Type` chính xác, `Content-ID` phù hợp và `Content-Disposition: inline`.
3. Attachment có filename, `Content-Disposition: attachment` và dữ liệu nguyên vẹn.
4. Cấu trúc `multipart/mixed`, `multipart/related` và `multipart/alternative` biểu diễn đúng quan hệ.
5. Email không bị thay đổi sai sau khi `saveChanges()`, `writeTo(...)` và parse lại.
6. Service gửi mail thực sự truyền `MimeMessage` đúng cho `JavaMailSender`, với trường hợp kiểm thử bằng mock/argument captor.
7. Các lỗi phổ biến được phát hiện bởi những assertion có ý nghĩa, thay vì chỉ phụ thuộc vào client hiển thị.

**Lưu ý về phạm vi:** Unit test giúp xác minh cách ứng dụng dựng message. Nó không tự chứng minh SMTP delivery, DKIM/SPF, việc hiển thị trong Gmail/Outlook hay nội dung attachment được người nhận mở thành công. Những điều đó cần các lớp kiểm thử khác.

## 2. Hiểu ba loại MIME part trước khi viết assertion

Một email phong phú thường có ba nhóm:

| Nhóm | MIME/Header thường gặp | Vai trò |
|---|---|---|
| Nội dung chính | `text/plain` hoặc `text/html` | Người nhận đọc nội dung thư |
| Inline resource | `image/png` hoặc `image/jpeg`, `Content-ID`, `Content-Disposition: inline` | HTML tham chiếu và hiển thị bên trong nội dung |
| Attachment | `application/pdf`, `Content-Disposition: attachment`, filename | Tệp độc lập để người nhận xem hoặc tải xuống |

MIME là một **cây**, không nhất thiết là danh sách phẳng. Một message có văn bản thuần, HTML, logo inline và PDF attachment có thể được biểu diễn khái quát:

~~~text
MimeMessage: multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     |
  |     |     +-- text/plain; charset=UTF-8
  |     |     +-- text/html; charset=UTF-8
  |     |           <img src="cid:order-logo">
  |     |
  |     +-- image/png
  |           Content-ID: <order-logo>
  |           Content-Disposition: inline
  |
  +-- application/pdf
        Content-Disposition: attachment
        filename="invoice.pdf"
~~~

Trong Spring, `MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED` tạo root mixed và một phần related bên trong. Khi gọi `setText(plainText, htmlText)`, helper có thể tạo multipart alternative ở vị trí phần nội dung trong related group.

Ý nghĩa của các subtype:

- `multipart/alternative`: các cách diễn đạt thay thế **cùng một nội dung**, thường plain trước HTML.
- `multipart/related`: nội dung gốc và các tài nguyên mà nội dung gốc tham chiếu.
- `multipart/mixed`: nhiều phần độc lập của email, thường gồm body và attachment.

### Vì sao không viết `getBodyPart(0)`, `getBodyPart(1)` ở mọi test?

Với mixed-related, part ảnh có thể nằm trong related group, còn attachment ở cấp mixed. Khi thêm bản text/plain hoặc ảnh thứ hai, thứ tự và độ sâu có thể thay đổi. Assertion chỉ dựa trên index cố định dễ vỡ hoặc nhận nhầm part.

Chiến lược bền hơn:

1. Kiểm tra kiểu root multipart nếu đó là một phần hợp đồng cấu trúc.
2. Duyệt cây MIME **đệ quy**.
3. Tìm part theo `isMimeType(...)`, disposition, filename hoặc Content-ID.
4. Kiểm tra giá trị đã parse/decoded; không so khớp toàn bộ raw MIME theo byte vì boundary và encoding có thể thay đổi.

## 3. Inline resource và attachment khác nhau ra sao?

Hai lời gọi tương tự về resource nhưng khác ngữ nghĩa:

~~~java
helper.addInline(
        "order-logo",
        logoResource,
        "image/png");

helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf");
~~~

`addInline(...)` gắn một tài nguyên mà HTML có thể tham chiếu. Với Content-ID `order-logo`, thẻ HTML dùng:

~~~html
<img src="cid:order-logo" alt="Logo đơn hàng">
~~~

`addAttachment(...)` thêm một file độc lập, thường xuất hiện dưới dạng tệp đính kèm trong giao diện email.

| Thuộc tính cần test | Inline image | PDF attachment |
|---|---|---|
| `Content-Type` | `image/png` | `application/pdf` |
| `Content-Disposition` | `inline` | `attachment` |
| `Content-ID` | Thường có, ví dụ `<order-logo>` | Không bắt buộc |
| `filename` | Không nhất thiết phải có | Cần khớp tên file dự kiến |
| HTML reference | `src="cid:order-logo"` | Không cần tham chiếu bằng CID |
| Dữ liệu | Byte PNG nguyên vẹn | Byte PDF nguyên vẹn |

**Content-ID không phải filename.** Một part ảnh có `Content-ID: <order-logo>` không cần mang tên `order-logo.png`. Tương tự, một PDF có filename `invoice.pdf` không nên bị coi là inline chỉ vì đuôi file được hỗ trợ hiển thị.

### Header có dấu ngoặc nhọn nhưng HTML không có

Thông thường:

~~~mime
Content-ID: <order-logo>
~~~

Trong HTML:

~~~html
<img src="cid:order-logo">
~~~

Khi gọi Spring:

~~~java
helper.addInline("order-logo", logoResource, "image/png");
~~~

Đối số Content-ID là `order-logo`; không thêm `cid:` hoặc dấu `< >` trong lời gọi. Helper tạo header tương ứng. Trong test, nên chuẩn hóa dấu ngoặc quanh giá trị header nếu muốn so khớp ý nghĩa.

## 4. Phân biệt unit test, MIME round-trip test và SMTP integration test

Có thể chia kiểm thử theo ba mức:

| Mức | Thao tác | Xác minh |
|---|---|---|
| Unit test trong bộ nhớ | Tạo `MimeMessage` và dùng helper, duyệt part | Logic dựng MIME và thuộc tính |
| MIME round-trip | `saveChanges` → `writeTo` → parse lại | Header/body và byte vẫn đọc đúng sau serialization |
| SMTP integration | Gửi tới Mailpit/GreenMail/SMTP sink thử nghiệm | Message thực sự đi qua SMTP transport và server nhận được |

Khi mục tiêu chỉ là **attachment, inline resource và Content-ID**, phần lớn assertion có thể thực hiện mà không khởi động Spring Boot hoặc SMTP server. Có thể dùng Jakarta Mail `Session` và `MimeMessage` trực tiếp trong JUnit.

Một nguyên tắc hữu ích:

**Đừng dùng SMTP integration test để phát hiện lỗi mà một unit test MIME đơn giản có thể phát hiện. Nhưng cũng đừng khẳng định unit test MIME chứng minh email client chắc chắn render ảnh đúng.**

## 5. Dependencies cần thiết

Trong dự án Spring Boot có hỗ trợ mail:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-mail` thường cung cấp Spring Mail và Jakarta Mail implementation tương thích với phiên bản Spring Boot đang dùng. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Mockito và các tiện ích test phổ biến theo cấu hình starter tương ứng.

Nếu dự án không dùng Spring Boot, cần khai báo phiên bản `spring-context-support`, Jakarta Mail API/implementation và thư viện test tương thích. Với Spring Framework 6+, package thường là `jakarta.mail.*`; code dự án Spring Framework 5 hoặc cũ hơn thường sử dụng `javax.mail.*`. Không trộn hai hệ package không tương thích trong cùng một ví dụ.

Ví dụ dùng Java 17+, JUnit Jupiter và AssertJ. Với Maven, khai báo các dependency tương đương trong `pom.xml`.

## 6. Tạo fixture có cả text, HTML, ảnh và attachment

Một fixture tốt nên có byte **được kiểm soát**, để sau khi MIME encode/decode ta có thể so sánh chính xác. Ở unit test kiểm tra cấu trúc, có thể dùng các mảng byte cố định; khi muốn test khả năng mở ảnh/PDF thật, cần dùng fixture file thực sự hợp lệ.

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class TestMailFactory {
    private TestMailFactory() {
    }

    public static final byte[] LOGO_BYTES =
            new byte[] {0x12, 0x34, 0x56, 0x78};
    public static final byte[] PDF_BYTES =
            new byte[] {0x25, 0x50, 0x44, 0x46, 0x2D};

    public static MimeMessage message() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.test");
        helper.setTo("customer@example.test");
        helper.setSubject("Xác nhận đơn hàng ORD-001");

        String plain = "Đơn hàng ORD-001 đã được xác nhận.";
        String html = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <img src="cid:order-logo"
                         alt="Logo đơn hàng">
                    <p>Đơn hàng <strong>ORD-001</strong>
                       đã được xác nhận.</p>
                  </body>
                </html>
                """;

        // Thiết lập body trước, resource liên quan sau.
        helper.setText(plain, html);
        helper.addInline(
                "order-logo",
                new ByteArrayResource(LOGO_BYTES),
                "image/png");
        helper.addAttachment(
                "invoice-ORD-001.pdf",
                new ByteArrayResource(PDF_BYTES),
                "application/pdf");

        return message;
    }
}
~~~

Trong fixture:

- `setText(plain, html)` tạo hai phiên bản body.
- `addInline` tạo part ảnh được tham chiếu bằng CID.
- `addAttachment` thêm PDF như tệp độc lập.
- `ByteArrayResource` cung cấp dữ liệu trong bộ nhớ và có thể mở `InputStream` mới khi cần.
- SMTP không được gọi; `MimeMessage` chỉ được dựng để test.

Các byte `LOGO_BYTES` và `PDF_BYTES` là dữ liệu minh họa **không phải tệp PNG/PDF hợp lệ**. Chúng phù hợp để test việc giữ byte và header, không phù hợp cho test render hay mở file trong email client. Khi test giao diện cuối, hãy dùng fixture PNG/PDF hợp lệ.

### Tại sao chọn ByteArrayResource?

Jakarta Mail có thể đọc resource khi tạo `DataHandler`, khi `saveChanges`, khi serialize hoặc lúc gửi. `ByteArrayResource` giữ byte cố định và cung cấp luồng đọc lại được; phù hợp unit test.

Không nên dùng một `InputStreamResource` bọc luồng **one-shot** cho attachment nếu quá trình dựng/serialize có thể đọc nhiều lần. Khi cần file thật, dùng `ClassPathResource` hoặc nguồn cung cấp stream mới trên mỗi lần đọc.

## 7. Tạo tiện ích duyệt cây MIME để kiểm tra mọi part

Một bài unit test đơn giản có thể đọc một `Multipart` rồi lấy từng `BodyPart`. Nhưng nếu dùng `MULTIPART_MODE_MIXED_RELATED`, HTML và inline image nằm trong multipart lồng nhau. Vì vậy nên có một test helper duyệt đệ quy.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimeTree {
    private MimeTree() {
    }

    public static List<Part> allParts(Part root)
            throws MessagingException, IOException {
        List<Part> parts = new ArrayList<>();
        walk(root, parts);
        return parts;
    }

    private static void walk(Part part, List<Part> parts)
            throws MessagingException, IOException {
        parts.add(part);

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    walk(multipart.getBodyPart(i), parts);
                }
            }
        }
    }

    public static Part requireMimeType(
            Part root, String mimeType) throws Exception {
        for (Part part : allParts(root)) {
            if (part.isMimeType(mimeType)) {
                return part;
            }
        }
        throw new AssertionError(
                "Missing MIME part: " + mimeType);
    }

    public static Part requireFilename(
            Part root, String filename) throws Exception {
        for (Part part : allParts(root)) {
            if (filename.equals(part.getFileName())) {
                return part;
            }
        }
        throw new AssertionError(
                "Missing attachment: " + filename);
    }

    public static Part requireContentId(
            Part root, String expectedId) throws Exception {
        for (Part part : allParts(root)) {
            if (expectedId.equals(contentId(part))) {
                return part;
            }
        }
        throw new AssertionError(
                "Missing Content-ID: " + expectedId);
    }

    public static String contentId(Part part)
            throws MessagingException {
        String[] headers = part.getHeader("Content-ID");
        if (headers == null || headers.length == 0) {
            return null;
        }

        String value = headers[0].trim();
        if (value.length() >= 2
                && value.startsWith("<")
                && value.endsWith(">")) {
            return value.substring(1, value.length() - 1);
        }
        return value;
    }
}
~~~

Tiện ích trên:

- Lấy cả **root**, các multipart group và leaf part; vì vậy có thể tìm `multipart/related` và `multipart/alternative`.
- Chỉ gọi `getContent()` khi gặp multipart; không cần decode toàn bộ attachment khi chỉ duyệt cấu trúc.
- Tìm part bằng MIME type, filename hoặc Content-ID thay vì dựa vào vị trí cố định.
- Chuẩn hóa dấu ngoặc nhọn của Content-ID khi cần so sánh.
- Không tự biến mọi giá trị Content-ID thành chữ thường vì đó là định danh tham chiếu, không phải tên header.

Nếu có hai ảnh cùng Content-Type, `requireMimeType(..., "image/png")` chỉ tìm ảnh đầu tiên. Khi test nhiều ảnh, dùng `requireContentId` để phân biệt hoặc bổ sung một hàm trả về danh sách các part cùng MIME type. Khi có nhiều attachment cùng filename, kiểm tra danh sách và quy tắc ứng dụng thay vì giả định filename luôn duy nhất.

### Tại sao chỉ kiểm tra leaf part vẫn chưa đủ?

Một cấu trúc phẳng `multipart/mixed` có thể chứa đủ HTML, PNG và PDF nhưng không thể hiện rõ ảnh PNG liên quan đến HTML. Kiểm tra sự tồn tại của các leaf part sẽ pass; trong khi một số email client vẫn có thể hiển thị ảnh như attachment.

Khi cấu trúc là một phần hợp đồng của composer, test nên xác nhận:

1. Root là mixed.
2. Có related group.
3. Related group chứa body HTML và các ảnh inline.
4. PDF attachment nằm như part độc lập dưới mixed root.

Trong các ứng dụng không cần khóa cấu trúc cụ thể, có thể ưu tiên assertion theo ngữ nghĩa; đừng gắn test cứng vào những chi tiết không ảnh hưởng yêu cầu sản phẩm.

## 8. Unit test kiểm tra ảnh inline và Content-ID

Ví dụ test với fixture `TestMailFactory` và `MimeTree` đã tạo:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class InlineResourceTest {
    @Test
    void embedsLogoWithCorrectContentId() throws Exception {
        MimeMessage message = TestMailFactory.message();

        Part image = MimeTree.requireContentId(
                message, "order-logo");

        assertThat(image.isMimeType("image/png")).isTrue();
        assertThat(image.getDisposition())
                .isEqualToIgnoringCase(Part.INLINE);

        assertThat(image.getHeader("Content-ID"))
                .containsExactly("<order-logo>");

        byte[] decoded;
        try (var input = image.getInputStream()) {
            decoded = input.readAllBytes();
        }
        assertThat(decoded)
                .containsExactly(TestMailFactory.LOGO_BYTES);
    }
}
~~~

Những assertion này xác nhận:

- Có MIME part chứa Content-ID chính xác.
- MIME type là `image/png`.
- Disposition là inline.
- Header raw có dấu `< >` chuẩn.
- Sau khi đọc part qua Jakarta Mail, byte vẫn giống fixture.

`Part.getInputStream()` cung cấp nội dung **đã qua bước decode Content-Transfer-Encoding** ở tầng Jakarta Mail; do đó nếu MIME body được Base64 encode, ta vẫn so sánh với byte gốc. Không nên so trực tiếp các dòng Base64 raw với byte file đầu vào.

### Vì sao dùng Content-ID để tìm ảnh?

Nếu HTML chứa:

~~~html
<img src="cid:order-logo">
<img src="cid:tracking-icon">
~~~

hai resource có thể đều là `image/png`. Tìm theo `image/png` rồi lấy part đầu tiên sẽ không chứng minh logo có đúng ID. Tìm theo Content-ID khiến test xác nhận đúng mapping mà email client cần.

### Không chỉ assert một phần chuỗi HTML

Test như:

~~~java
assertThat(html).contains("cid:order-logo");
~~~

là hữu ích nhưng **chưa đủ**: HTML có thể tham chiếu đúng chuỗi nhưng MIME message không có part nào mang Content-ID đó. Một test đầy đủ cần kiểm tra cả **reference trong HTML** lẫn **part tương ứng**.

## 9. Kiểm tra text/html tham chiếu đúng ảnh

Với fixture trên, có thể truy cập body HTML bằng cách tìm đúng MIME type rồi đọc `getContent()`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class HtmlReferenceTest {
    @Test
    void htmlReferencesExistingInlineImage() throws Exception {
        MimeMessage message = TestMailFactory.message();

        Part htmlPart = MimeTree.requireMimeType(
                message, "text/html");
        String html = (String) htmlPart.getContent();

        assertThat(html)
                .contains("src=\"cid:order-logo\"");

        Part matchingImage = MimeTree.requireContentId(
                message, "order-logo");
        assertThat(matchingImage.isMimeType("image/png")).isTrue();
        assertThat(matchingImage.getDisposition())
                .isEqualToIgnoringCase(Part.INLINE);
    }
}
~~~

Test này xác nhận cả hai phía của quan hệ:

~~~text
HTML                                MIME part
src="cid:order-logo" -----------> Content-ID: <order-logo>
                                      |
                                      +-- Content-Type: image/png
                                      +-- Disposition: inline
~~~

### Nội dung HTML có đúng định dạng không?

Chuỗi HTML có thể chứa các khoảng trắng, dấu nháy đơn/đôi và thuộc tính theo thứ tự khác nhau:

~~~html
<img alt="Logo" src='cid:order-logo'>
~~~

Một assert chỉ tìm `src="cid:order-logo"` có thể fail dù HTML có ý nghĩa tương đương. Nếu template HTML phức tạp, có thể dùng HTML parser như Jsoup để truy xuất `img[src]` và so sánh URI; đó là lựa chọn cho test **template**. Không cần thêm HTML parser chỉ để xác nhận một fixture đơn giản.

### CID phải mang cùng giá trị tham chiếu

Không nên chấp nhận một test mà HTML dùng `cid:order-logo` nhưng part có `Content-ID: <logo>`; email có thể được SMTP accepted nhưng ảnh không xuất hiện. Cũng không nên thay `cid:` bằng URL `https:` mà vẫn khẳng định đang test **inline MIME resource**: remote image và CID image có mô hình gửi khác nhau.

## 10. Unit test attachment: filename, disposition, Content-Type và byte

Một attachment không được xác nhận chỉ bằng lời gọi `addAttachment`. Hãy kiểm tra kết quả trong `MimeMessage`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class AttachmentTest {
    @Test
    void attachesInvoiceAsIndependentPdf() throws Exception {
        MimeMessage message = TestMailFactory.message();

        Part pdf = MimeTree.requireFilename(
                message, "invoice-ORD-001.pdf");

        assertThat(pdf.isMimeType("application/pdf")).isTrue();
        assertThat(pdf.getDisposition())
                .isEqualToIgnoringCase(Part.ATTACHMENT);
        assertThat(pdf.getFileName())
                .isEqualTo("invoice-ORD-001.pdf");

        byte[] decoded;
        try (var input = pdf.getInputStream()) {
            decoded = input.readAllBytes();
        }
        assertThat(decoded)
                .containsExactly(TestMailFactory.PDF_BYTES);
    }
}
~~~

**Filename và disposition là hai thuộc tính khác nhau.** Một MIME part có filename `invoice.pdf` nhưng `Content-Disposition: inline` không nhất thiết được email client coi là attachment thông thường. Tương tự, một part có disposition attachment nhưng không có filename có thể xuất hiện như tệp “unnamed” hoặc được hiển thị khác nhau.

### Tên file Unicode

Nếu tệp có tên `hóa-đơn-đã-thanh-toán.pdf`, Jakarta Mail có thể mã hóa tham số filename bằng cơ chế tương thích MIME. Unit test nên xem giá trị **đã giải mã từ `getFileName()`**:

~~~java
assertThat(pdf.getFileName())
        .isEqualTo("hóa-đơn-đã-thanh-toán.pdf");
~~~

Không nên snapshot cứng toàn bộ raw `Content-Disposition` header rồi yêu cầu nó giống từng byte giữa các implementation và version. Một số thư viện/provider có thể biểu diễn tên tệp theo các cách mã hóa hợp lệ khác nhau.

### Content-Type không phải bằng chứng file hợp lệ

`addAttachment(..., "application/pdf")` đặt media type mà ứng dụng cung cấp. Nếu byte là dữ liệu rác, assertion `isMimeType("application/pdf")` vẫn có thể pass.

Phân biệt:

1. **MIME assembly test:** kiểm tra header và byte đã được bảo toàn.
2. **Resource validation test:** kiểm tra byte file thực là PDF/PNG hợp lệ theo tiêu chuẩn sản phẩm.
3. **Email client test:** kiểm tra file tới mailbox có thể tải/mở.

Không nên coi một mảng byte minh họa là file PDF hợp lệ chỉ vì nó bắt đầu bằng `%PDF-`.

## 11. Kiểm tra đúng vị trí của inline resource và attachment trong MIME tree

Kiểm tra MIME part có tồn tại là bước đầu, nhưng khi mục tiêu là **khả năng hiển thị trên client**, còn phải kiểm tra quan hệ cha–con. Ví dụ, chỉ có ba leaf `text/html`, `image/png`, `application/pdf` không chứng minh ảnh được đặt trong nhóm related.

Với `MULTIPART_MODE_MIXED_RELATED` và fixture ở phần 6, một test cấu trúc có thể viết:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class NestedMimeTreeTest {
    @Test
    void nestsInlineImageUnderRelatedAndPdfUnderMixed()
            throws Exception {
        MimeMessage message = TestMailFactory.message();

        assertThat(message.isMimeType("multipart/mixed"))
                .isTrue();

        Multipart mixed = (Multipart) message.getContent();
        assertThat(mixed.getCount()).isEqualTo(2);

        BodyPart relatedContainer = mixed.getBodyPart(0);
        assertThat(relatedContainer.isMimeType("multipart/related"))
                .isTrue();

        BodyPart pdf = mixed.getBodyPart(1);
        assertThat(pdf.isMimeType("application/pdf")).isTrue();
        assertThat(pdf.getDisposition())
                .isEqualToIgnoringCase(Part.ATTACHMENT);

        Multipart related =
                (Multipart) relatedContainer.getContent();
        assertThat(related.getCount()).isEqualTo(2);

        BodyPart alternativeContainer = related.getBodyPart(0);
        assertThat(
                alternativeContainer.isMimeType("multipart/alternative"))
                .isTrue();

        BodyPart logo = related.getBodyPart(1);
        assertThat(logo.isMimeType("image/png")).isTrue();
        assertThat(MimeTree.contentId(logo))
                .isEqualTo("order-logo");
    }
}
~~~

Test trên kiểm tra **một contract cấu trúc cụ thể** của helper khi chọn mixed-related và chỉ thêm một ảnh, một PDF. Nếu thêm ảnh thứ hai, related group sẽ có thêm part; nếu thêm attachment thứ hai, mixed root sẽ có thêm part. Khi đó cần cập nhật assertion theo hợp đồng mới, không hiểu một số `getCount()` là quy tắc MIME chung cho mọi email.

### Kiểm tra cấu trúc alternative

Tiếp tục từ `alternativeContainer`:

~~~java
Multipart alternative =
        (Multipart) alternativeContainer.getContent();

assertThat(alternative.getCount()).isEqualTo(2);
assertThat(alternative.getBodyPart(0).isMimeType("text/plain"))
        .isTrue();
assertThat(alternative.getBodyPart(1).isMimeType("text/html"))
        .isTrue();
~~~

Trong `multipart/alternative`, quy ước MIME là đặt nội dung từ ít phong phú đến phong phú hơn, nên plain text thường trước HTML. `MimeMessageHelper.setText(plainText, htmlText)` quản lý việc dựng hai alternative. Không tự tách hai body thành các attachment độc lập rồi cho rằng mail client sẽ chọn đúng.

### Khi nào không nên khóa chặt vị trí?

Nếu ứng dụng sử dụng thư viện khác hoặc thay đổi multipart mode mà vẫn giữ đúng chức năng, test quá chi tiết về chỉ số part có thể fail không cần thiết. Một mô hình hợp lý:

- **Test chức năng phổ biến:** kiểm tra mọi inline resource và attachment có đúng nội dung/headers.
- **Test contract MIME của composer:** kiểm tra cấu trúc mixed-related cụ thể khi đó là yêu cầu.
- **Integration/client test:** kiểm tra cách client thực sự hiển thị.

## 12. MIME round-trip: serialize rồi parse lại

Một `MimeMessage` trong bộ nhớ có thể chứa các object `DataHandler` và resource chưa được mã hóa thành raw MIME. Trước khi gửi, Jakarta Mail sẽ tạo các header/encoding/boundary cần thiết. Vì vậy **serialize rồi parse lại** là cách kiểm tra mạnh hơn việc chỉ đọc object mới tạo.

~~~text
MimeMessageHelper
       |
       v
MimeMessage trong RAM
       |
       v
saveChanges()
       |
       v
writeTo(OutputStream)
       |
       v
Raw RFC 822 / MIME bytes
       |
       v
new MimeMessage(Session, InputStream)
       |
       v
Kiểm tra multipart, Content-ID, byte decoded
~~~

Ví dụ:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;

public final class MimeRoundTrip {
    private MimeRoundTrip() {
    }

    public static MimeMessage serializeAndParse(
            MimeMessage original) throws Exception {
        original.saveChanges();

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        original.writeTo(out);

        Session parserSession =
                Session.getInstance(new Properties());
        return new MimeMessage(
                parserSession,
                new ByteArrayInputStream(out.toByteArray()));
    }
}
~~~

`saveChanges()` yêu cầu message hoàn thiện các header và metadata cần thiết. `writeTo(...)` chuyển message thành stream byte thực. Constructor `MimeMessage(Session, InputStream)` parse lại dữ liệu đó mà không kết nối SMTP.

### Test nội dung còn nguyên sau round-trip

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class MimeRoundTripTest {
    @Test
    void preservesInlineAndAttachmentAfterSerialization()
            throws Exception {
        MimeMessage parsed = MimeRoundTrip.serializeAndParse(
                TestMailFactory.message());

        assertThat(parsed.isMimeType("multipart/mixed"))
                .isTrue();

        Part logo = MimeTree.requireContentId(
                parsed, "order-logo");
        assertThat(logo.isMimeType("image/png")).isTrue();
        assertThat(logo.getDisposition())
                .isEqualToIgnoringCase(Part.INLINE);

        try (var input = logo.getInputStream()) {
            assertThat(input.readAllBytes())
                    .containsExactly(TestMailFactory.LOGO_BYTES);
        }

        Part pdf = MimeTree.requireFilename(
                parsed, "invoice-ORD-001.pdf");
        assertThat(pdf.isMimeType("application/pdf")).isTrue();
        assertThat(pdf.getDisposition())
                .isEqualToIgnoringCase(Part.ATTACHMENT);

        try (var input = pdf.getInputStream()) {
            assertThat(input.readAllBytes())
                    .containsExactly(TestMailFactory.PDF_BYTES);
        }
    }
}
~~~

Round-trip có thể phát hiện lỗi không rõ khi chỉ thao tác với object, chẳng hạn header bị mã hóa sai, Content-ID bị mất, MIME part không serialize được hoặc nguồn attachment không cung cấp lại stream.

**Giới hạn:** Parse lại message không chứng minh email đã được SMTP accepted, và cũng không chứng minh client cuối cùng sẽ tự động hiển thị ảnh. Nó chứng minh tính đúng đắn trong phạm vi serializer/parser đang dùng.

### Đừng snapshot toàn bộ raw MIME

Một raw message có thể chứa boundary ngẫu nhiên, header Date/Message-ID, line wrapping và cách Base64 folding phụ thuộc implementation:

~~~mime
Content-Type: multipart/mixed;
 boundary="----=_Part_42_238230984.1780000000000"
~~~

Không nên assert **raw bytes của cả email giống hệt một file snapshot** nếu yêu cầu chỉ là attachment/CID. Thay vào đó, parse message rồi so sánh thuộc tính và byte **đã decode**. Snapshot toàn bộ có thể fail vì chi tiết không liên quan chức năng.

## 13. Kiểm thử service thực tế bằng Mockito ArgumentCaptor

Trong ứng dụng, code dựng message thường nằm trong một service, ví dụ:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class InvoiceMailService {
    private final JavaMailSender sender;

    public InvoiceMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(
            String recipient,
            byte[] logo,
            byte[] invoicePdf) {
        MimeMessage message = sender.createMimeMessage();
        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                    StandardCharsets.UTF_8.name());

            helper.setFrom("orders@example.test");
            helper.setTo(recipient);
            helper.setSubject("Hóa đơn ORD-001");
            helper.setText(
                    "Hóa đơn ORD-001 đính kèm.",
                    "<p><img src=\"cid:order-logo\">"
                            + "Hóa đơn ORD-001 đính kèm.</p>");
            helper.addInline(
                    "order-logo",
                    new ByteArrayResource(logo),
                    "image/png");
            helper.addAttachment(
                    "invoice-ORD-001.pdf",
                    new ByteArrayResource(invoicePdf),
                    "application/pdf");
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot compose invoice email", ex);
        }

        sender.send(message);
    }
}
~~~

Trong code trên, `JavaMailSender` là dependency và `send(MimeMessage)` chỉ được gọi sau khi compose. Việc xây dựng MIME không yêu cầu kết nối SMTP trước khi `send(...)` chạy.

### Test capture message truyền vào sender

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class InvoiceMailServiceTest {
    @Test
    void sendsMessageContainingExpectedPdfAndLogo()
            throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        Session session = Session.getInstance(new Properties());

        when(sender.createMimeMessage())
                .thenReturn(new MimeMessage(session));

        InvoiceMailService service =
                new InvoiceMailService(sender);

        service.sendInvoice(
                "customer@example.test",
                TestMailFactory.LOGO_BYTES,
                TestMailFactory.PDF_BYTES);

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);
        verify(sender).send(captor.capture());

        MimeMessage parsed = MimeRoundTrip.serializeAndParse(
                captor.getValue());

        assertThat(parsed.getSubject())
                .isEqualTo("Hóa đơn ORD-001");

        Part logo = MimeTree.requireContentId(
                parsed, "order-logo");
        assertThat(logo.isMimeType("image/png")).isTrue();

        Part pdf = MimeTree.requireFilename(
                parsed, "invoice-ORD-001.pdf");
        assertThat(pdf.getDisposition())
                .isEqualToIgnoringCase(Part.ATTACHMENT);

        try (var input = pdf.getInputStream()) {
            assertThat(input.readAllBytes())
                    .containsExactly(TestMailFactory.PDF_BYTES);
        }
    }
}
~~~

Với Mockito:

- `when(sender.createMimeMessage())` trả một MimeMessage thật trong bộ nhớ.
- `sender.send(...)` được mock nên **không gửi thư ra mạng**.
- `ArgumentCaptor` lấy đúng message mà service truyền tới sender.
- `MimeRoundTrip` kiểm tra kết quả MIME sau serialization.

Đây là cách kết hợp **unit test của service** với việc kiểm tra cấu trúc message thật. Nó mạnh hơn:

~~~java
verify(sender).send(any(MimeMessage.class));
~~~

vì verify đơn thuần chỉ chứng minh phương thức được gọi, không nói gì về nội dung attachment hay Content-ID.

## 14. Kiểm thử khi ứng dụng dùng MimeMessagePreparator

Một phong cách khác của Spring Mail là truyền lambda `MimeMessagePreparator` cho `JavaMailSender.send(...)`:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class PreparatorMailService {
    private final JavaMailSender sender;

    public PreparatorMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient, byte[] logoBytes) {
        sender.send(message -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");
            helper.setFrom("orders@example.test");
            helper.setTo(recipient);
            helper.setSubject("Thông báo mới");
            helper.setText(
                    "<img src=\"cid:status-icon\">"
                            + "<p>Đơn hàng đã xác nhận.</p>",
                    true);
            helper.addInline(
                    "status-icon",
                    new org.springframework.core.io.ByteArrayResource(
                            logoBytes),
                    "image/png");
        });
    }
}
~~~

Ở dạng này, code dựng `MimeMessage` nằm **bên trong callback**. Mockito mock mặc định của `sender.send(preparator)` **không tự chạy callback**. Vì thế test kiểu:

~~~java
verify(sender).send(any(MimeMessagePreparator.class));
~~~

chỉ xác nhận preparator đã được truyền, chưa chứng minh nó tạo đúng message.

### Dùng Mockito Answer để thực thi preparator trên MimeMessage thật

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;

import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

class PreparatorMailServiceTest {
    @Test
    void preparatorAddsInlineImageWithExpectedCid()
            throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        Session session = Session.getInstance(new Properties());
        AtomicReference<MimeMessage> prepared =
                new AtomicReference<>();

        doAnswer(call -> {
            MimeMessagePreparator preparator =
                    call.getArgument(0);
            MimeMessage message = new MimeMessage(session);
            preparator.prepare(message);
            prepared.set(message);
            return null;
        }).when(sender).send(any(MimeMessagePreparator.class));

        new PreparatorMailService(sender)
                .send("customer@example.test", TestMailFactory.LOGO_BYTES);

        MimeMessage message = MimeRoundTrip.serializeAndParse(
                prepared.get());

        Part logo = MimeTree.requireContentId(
                message, "status-icon");
        assertThat(logo.isMimeType("image/png")).isTrue();
        assertThat(logo.getDisposition())
                .isEqualToIgnoringCase(Part.INLINE);

        String html = (String) MimeTree.requireMimeType(
                message, "text/html").getContent();
        assertThat(html).contains("cid:status-icon");
    }
}
~~~

Trong test này, `doAnswer` tạo message thật và gọi `preparator.prepare(message)`, nên nội dung được dựng đúng như khi sender thực thi callback. Test không mở kết nối mạng. Lỗi xảy ra khi prepare sẽ được ném trong test và giúp phát hiện vấn đề ở bước composition.

**Lưu ý khác biệt giữa API:** Nếu service dùng `send(MimeMessage)`, capture message; nếu service dùng `send(MimeMessagePreparator)`, mock cần thực thi callback thì mới kiểm tra nội dung được. Đừng trộn hai phương thức và tưởng cùng một cách mock là tương đương.

## 15. Kiểm tra nhiều ảnh inline và Content-ID duy nhất

Một HTML template có thể dùng logo, hình minh họa và biểu tượng khác nhau:

~~~html
<header>
  <img src="cid:header-logo" alt="Logo">
</header>
<main>
  <img src="cid:order-status" alt="Trạng thái đơn hàng">
</main>
~~~

Composer:

~~~java
helper.setText(html, true);

helper.addInline(
        "header-logo",
        new ByteArrayResource(headerLogoBytes),
        "image/png");

helper.addInline(
        "order-status",
        new ByteArrayResource(orderStatusBytes),
        "image/png");
~~~

Test không nên lấy “PNG đầu tiên”. Hãy tìm bằng Content-ID:

~~~java
Part headerLogo = MimeTree.requireContentId(
        message, "header-logo");
Part orderStatus = MimeTree.requireContentId(
        message, "order-status");

assertThat(headerLogo).isNotSameAs(orderStatus);
assertThat(headerLogo.isMimeType("image/png")).isTrue();
assertThat(orderStatus.isMimeType("image/png")).isTrue();
~~~

### Phát hiện Content-ID trùng

Hai inline part có cùng Content-ID khiến tham chiếu không rõ ràng. Có thể kiểm tra tất cả MIME part:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import java.util.HashSet;
import java.util.Set;

Set<String> seenIds = new HashSet<>();
for (Part part : MimeTree.allParts(message)) {
    String contentId = MimeTree.contentId(part);
    if (contentId == null) {
        continue;
    }

    assertThat(seenIds.add(contentId))
            .as("Content-ID must be unique: %s", contentId)
            .isTrue();
}
~~~

Đây là quy tắc test đơn giản dành cho những message mà ứng dụng muốn Content-ID là duy nhất. Trong các cấu trúc MIME phức tạp, quan hệ `multipart/alternative` hoặc các cơ chế tương thích đặc thù có thể cần chính sách phân giải khác; với inline resource của newsletter/receipt thông thường, ID duy nhất là lựa chọn rõ ràng.

### Kiểm tra tất cả reference trong HTML đều có MIME part

Khi template có nhiều ảnh, một test tổng quát có thể trích các reference `cid:...` và so với Content-ID:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashSet;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

String html = (String) MimeTree.requireMimeType(
        message, "text/html").getContent();

Pattern cidPattern =
        Pattern.compile("cid:([A-Za-z0-9._-]+)");
Matcher matcher = cidPattern.matcher(html);

Set<String> referencedIds = new HashSet<>();
while (matcher.find()) {
    referencedIds.add(matcher.group(1));
}

assertThat(referencedIds)
        .containsExactlyInAnyOrder(
                "header-logo", "order-status");

for (String id : referencedIds) {
    Part image = MimeTree.requireContentId(message, id);
    assertThat(image.getDisposition())
            .isEqualToIgnoringCase(Part.INLINE);
}
~~~

Regex trên là test helper **cho quy ước Content-ID đơn giản của ứng dụng**, không phải parser tổng quát của RFC 2392. CID URL có thể chứa ký tự được percent-encode, HTML có thể tham chiếu ảnh qua CSS hoặc thuộc tính khác. Nếu template hỗ trợ URI phức tạp, nên dùng HTML parser và URI decoding đúng chuẩn thay vì khẳng định regex này bao phủ mọi trường hợp.

### Kiểm tra chiều ngược lại

Ngoài việc đảm bảo mọi CID trong HTML có part tương ứng, có thể kiểm tra không có inline part bị quên dùng (trừ khi thiết kế có chủ ý):

~~~text
HTML tham chiếu: {header-logo, order-status}
MIME inline IDs: {header-logo, order-status}

Hai tập hợp cần trùng nhau theo policy của template.
~~~

Kiểm tra chiều ngược giúp phát hiện attachment “thừa” làm tăng dung lượng email. Nhưng không phải mọi inline resource đều nhất thiết phải được reference trong một bản HTML alternative; hãy áp quy tắc theo template của ứng dụng.

## 16. Kiểm tra nhiều attachment: đúng từng filename, không nhầm nội dung

Ví dụ một email có hai PDF:

~~~java
helper.setText(
        "Đính kèm hóa đơn và điều khoản.",
        false);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoiceBytes),
        "application/pdf");
helper.addAttachment(
        "terms.pdf",
        new ByteArrayResource(termsBytes),
        "application/pdf");
~~~

Khi test, hãy tìm theo tên:

~~~java
Part invoice = MimeTree.requireFilename(
        message, "invoice.pdf");
Part terms = MimeTree.requireFilename(
        message, "terms.pdf");

try (var invoiceStream = invoice.getInputStream();
     var termsStream = terms.getInputStream()) {

    assertThat(invoiceStream.readAllBytes())
            .containsExactly(invoiceBytes);
    assertThat(termsStream.readAllBytes())
            .containsExactly(termsBytes);
}
~~~

Nếu tìm hai part theo `application/pdf` rồi mặc định phần đầu là invoice, phần thứ hai là terms, test sẽ mong manh và có thể không phát hiện nhầm nội dung. Filename là một key hợp lý khi ứng dụng bảo đảm mỗi attachment có tên riêng.

### Có cần kiểm tra thứ tự attachment?

MIME part order có thể ảnh hưởng một số client, nhưng ứng dụng không phải lúc nào cũng cần bảo đảm người nhận thấy thứ tự file. Nếu yêu cầu nghiệp vụ có thứ tự đính kèm, hãy viết test về thứ tự trong cấu trúc xác định. Nếu không, ưu tiên kiểm tra tập filename và byte theo ánh xạ, tránh test fail chỉ vì code đổi thứ tự thêm file.

### Không biến filename thành đường dẫn nguy hiểm

Tên file hiển thị nên là tên do ứng dụng tạo và không chứa đường dẫn như:

~~~text
../../internal/private.pdf
C:\secrets\key.txt
~~~

Trong test cho attachment nhận từ người dùng hoặc nguồn bên ngoài, có thể xác minh tên file đã được chuẩn hóa và không chứa path separator/control characters. Đây là **kiểm tra bảo mật dữ liệu đầu vào**, tách biệt với assertion MIME thông thường.

## 17. Negative test: khi code thêm sai loại part

Một unit test tốt không chỉ xác nhận happy path mà còn giúp phát hiện kiểu sai có khả năng xảy ra khi refactor:

### Nhầm addAttachment thành addInline

Giả sử developer đổi:

~~~java
helper.addAttachment(
        "invoice.pdf", pdfResource, "application/pdf");
~~~

thành:

~~~java
helper.addInline(
        "invoice",
        pdfResource,
        "application/pdf");
~~~

Email có thể vẫn chứa đúng byte PDF nhưng disposition trở thành inline và không có filename như mong muốn. Test attachment ở phần 10 sẽ phát hiện vì:

~~~java
assertThat(pdf.getDisposition())
        .isEqualToIgnoringCase(Part.ATTACHMENT);
~~~

Vì vậy **chỉ so sánh byte là chưa đủ**: một part chứa byte đúng nhưng ý nghĩa gửi sai vẫn có thể làm người nhận khó tải file.

### Nhầm addInline thành addAttachment

~~~java
helper.addAttachment(
        "logo.png",
        logoResource,
        "image/png");
~~~

HTML có thể vẫn tham chiếu `cid:order-logo`, nhưng part vừa thêm không tự có Content-ID mong muốn. Test `MimeTree.requireContentId(message, "order-logo")` sẽ fail. Tên file và MIME type không thể thay thế header Content-ID.

### Dùng helper không bật multipart

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message, false, "UTF-8");

helper.addAttachment("invoice.pdf", pdfResource);
~~~

Với helper không ở chế độ multipart, việc thêm attachment/inline resource không phù hợp và có thể bị từ chối bằng exception. Nên test rằng composer **chọn multipart mode phù hợp** khi nghiệp vụ yêu cầu file đính kèm hoặc ảnh CID.

### CID trong HTML sai hoặc khác chữ hoa/thường

~~~html
<img src="cid:order-logo">
~~~

~~~java
helper.addInline("Order-Logo", logoResource, "image/png");
~~~

Không nên giả định mọi mail client sẽ coi hai ID là giống nhau. Hãy dùng Content-ID ổn định, nhất quán giữa template và composer; test so khớp chính xác tên ID do ứng dụng định nghĩa.

### Trùng Content-ID

~~~java
helper.addInline(
        "logo",
        resourceA,
        "image/png");
helper.addInline(
        "logo",
        resourceB,
        "image/jpeg");
~~~

Message có thể chứa hai body part cùng ID. Test cần kiểm tra ID là duy nhất theo chính sách thay vì chỉ xác nhận một trong hai part tồn tại.

### Thiếu attachment nhưng vẫn gọi sender

Nếu ứng dụng bắt buộc gửi hóa đơn nhưng repository trả file null/rỗng, service có thể gửi một email thông báo không có hóa đơn. Một test nên kiểm tra **validation nghiệp vụ**:

~~~java
assertThatThrownBy(() ->
        service.sendInvoice(
                "customer@example.test",
                validLogo,
                null))
        .isInstanceOf(IllegalArgumentException.class);
~~~

Assertion này chỉ đúng nếu service được thiết kế **từ chối null trước khi gọi sender**. Kiểu exception cụ thể tùy hợp đồng của ứng dụng; không nên trông chờ Jakarta Mail tự thay thế validation đầu vào.

## 18. Kiểm tra dữ liệu nhị phân sau Content-Transfer-Encoding

Một tệp đính kèm không được gửi qua raw SMTP giống như byte ban đầu; MIME thường encode dữ liệu nhị phân bằng Base64:

~~~mime
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

JVBERi0xLjQK...
~~~

Một ảnh inline cũng có thể có:

~~~mime
Content-Type: image/png
Content-ID: <order-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

iVBORw0KGgo...
~~~

Để kiểm tra byte:

~~~java
try (var stream = part.getInputStream()) {
    byte[] actual = stream.readAllBytes();
    assertThat(actual).containsExactly(expectedBytes);
}
~~~

Không nên so raw encoded Base64 string trong message với chuỗi tự tạo, vì line wrapping và implementation có thể thay đổi. Byte decoded mới là dữ liệu mà ứng dụng muốn gửi.

### Không nhất thiết assert Content-Transfer-Encoding bằng một giá trị cố định

Tùy kiểu MIME, nội dung, thư viện và transport, text part có thể dùng quoted-printable, Base64 hoặc encoding khác. Với các part nhị phân, Base64 rất phổ biến, nhưng test chỉ nên cố định `Content-Transfer-Encoding` nếu yêu cầu nghiệp vụ hoặc khả năng tương thích thực sự đòi hỏi.

Các assertion nên ưu tiên:

1. Byte decoded khớp byte nguồn.
2. Content-Type được khai báo đúng.
3. Disposition phù hợp.
4. CID hoặc filename phù hợp.

Tránh test phụ thuộc implementation detail không cần thiết.

### Byte array trong test có thể không phải file hợp lệ

Đối với unit test assembly, dữ liệu:

~~~java
byte[] fakePng = new byte[] {1, 2, 3};
~~~

có thể đủ để kiểm tra không bị thay đổi byte. Nhưng nếu muốn khẳng định người nhận mở được file PNG, cần fixture ảnh hợp lệ; không thể suy ra tính hợp lệ từ MIME header.

## 19. Test với ClassPathResource và fixture file thật

Khi muốn kiểm tra byte của attachment/resource giống file đã phát hành cùng ứng dụng, sử dụng `ClassPathResource`:

~~~java
import org.springframework.core.io.ClassPathResource;

helper.setText(html, true);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail-test/logo.png"),
        "image/png");

helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail-test/invoice.pdf"),
        "application/pdf");
~~~

Giả sử dự án có:

~~~text
src/test/resources/
└── mail-test/
    ├── logo.png
    └── invoice.pdf
~~~

Test có thể so sánh bytes:

~~~java
ClassPathResource expectedPdf =
        new ClassPathResource("mail-test/invoice.pdf");

byte[] original;
try (var input = expectedPdf.getInputStream()) {
    original = input.readAllBytes();
}

Part attached = MimeTree.requireFilename(
        parsedMessage, "invoice.pdf");

try (var input = attached.getInputStream()) {
    assertThat(input.readAllBytes())
            .containsExactly(original);
}
~~~

`ClassPathResource` phù hợp với fixture nhỏ và bất biến. Trong production, có thể cần streaming từ object storage hoặc filesystem, nhưng chiến lược đọc nhiều lần và giới hạn kích thước vẫn phải được xem xét.

### Kiểm tra resource bị thiếu

Nếu path `mail-test/logo.png` không tồn tại:

- `ClassPathResource` vẫn có thể được khởi tạo.
- Lỗi có thể xuất hiện khi mở input stream hoặc serialize/gửi message.

Do đó, một test chỉ gọi `new ClassPathResource(...)` không chứng minh tài nguyên tồn tại. Hãy kiểm tra `exists()` hoặc buộc message thực sự đọc resource bằng round-trip:

~~~java
ClassPathResource logo =
        new ClassPathResource("mail-test/logo.png");

assertThat(logo.exists()).isTrue();
~~~

Nếu composer phải báo lỗi rõ ràng khi resource thiếu, hãy kiểm tra exception ở **đúng giai đoạn** thực sự đọc file, không giả định mọi overload của `addInline` đều load byte ngay lúc được gọi.

### Đừng phụ thuộc đường dẫn tuyệt đối của máy chạy CI

Đường dẫn như `C:\Users\developer\Desktop\invoice.pdf` hoặc `/tmp/invoice.pdf` dễ làm test chỉ chạy trên một máy. Fixture nên nằm trong classpath hoặc được tạo trong thư mục tạm qua JUnit `@TempDir`, với byte do test kiểm soát.

## 20. Resource chỉ đọc một lần: nguy cơ khi dùng InputStreamResource

Một số nguồn attachment chỉ có một stream đang mở. Nếu stream được đọc lúc dựng message, lần serialize hoặc lần gửi tiếp theo có thể không còn dữ liệu:

~~~text
InputStream một lần
      |
      v
Mail composer đọc
      |
      v
InputStream đã tới EOF hoặc bị đóng
      |
      v
Jakarta Mail serialize lần nữa
      |
      v
Attachment rỗng hoặc IOException
~~~

`InputStreamResource` thường bọc một `InputStream` cụ thể, không phải một nhà máy tạo luồng mới. Với Spring Mail, nguồn attachment nên có khả năng cung cấp `InputStream` mới khi cần (đặc biệt khi thư viện phải kiểm tra kích thước, encode hoặc serialize). `ByteArrayResource` và `ClassPathResource` thường phù hợp hơn trong ví dụ/test.

Đối với file lớn, tránh đọc toàn bộ vào byte array nếu có thể gây áp lực heap. Có thể thiết kế một `InputStreamSource` cung cấp stream mới từ file/object store trên mỗi lần đọc, đồng thời bảo đảm:

- Quyền truy cập resource vẫn hợp lệ trong suốt thời gian tạo/gửi mail.
- Nguồn dữ liệu không đổi giữa các lần đọc.
- Dữ liệu có checksum hoặc một định danh version nếu cần.
- Có timeout, giới hạn dung lượng và xử lý lỗi I/O phù hợp.

### Test phát hiện resource không đọc lại được

Một cách tiếp cận:

1. Dựng message từ resource.
2. Serialize một lần.
3. Parse và kiểm tra bytes.
4. Nếu nghiệp vụ yêu cầu gửi lại/copy message, thử serialize lần nữa từ cùng nguồn hoặc xây message mới.
5. Kiểm tra resource vẫn có thể mở stream cần thiết.

Không nên cố ép mọi resource một lần thành reusable mà không hiểu adapter. Khi ứng dụng gửi qua queue hoặc outbox sau nhiều phút, lưu **resource reference bền vững** hoặc snapshot được bảo vệ, tránh giữ một `InputStream` mở từ request HTTP đến lúc worker chạy.

## 21. Test nội dung plain text và HTML cùng với resource

Attachment và inline resource thường đi kèm email HTML. Một unit test nên xác nhận bản plain text và HTML có nội dung quan trọng tương ứng, chứ không chỉ có đủ part:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class AlternativeBodyTest {
    @Test
    void containsReadableTextAndHtml() throws Exception {
        MimeMessage message = TestMailFactory.message();

        Part plainPart =
                MimeTree.requireMimeType(message, "text/plain");
        Part htmlPart =
                MimeTree.requireMimeType(message, "text/html");

        String plain = (String) plainPart.getContent();
        String html = (String) htmlPart.getContent();

        assertThat(plain).contains("ORD-001");
        assertThat(html).contains("ORD-001");
        assertThat(html).contains("cid:order-logo");

        assertThat(plainPart.getContentType())
                .containsIgnoringCase("charset=UTF-8");
        assertThat(htmlPart.getContentType())
                .containsIgnoringCase("charset=UTF-8");
    }
}
~~~

Đây là kiểm tra nội dung/thông tin quan trọng, không phải snapshot toàn bộ HTML. Nếu body text và HTML cùng chứa mã đơn hàng, test ít phụ thuộc whitespace, CSS hoặc thứ tự thuộc tính.

### Khi nào cần test nội dung đã escape HTML?

Nếu tên khách hàng đến từ dữ liệu bên ngoài:

~~~text
Tên: <script>alert(1)</script>
~~~

HTML template phải escape dữ liệu phù hợp để không chèn HTML/JavaScript tùy ý vào message. Đây là kiểm tra **template rendering và input safety**, có thể viết test riêng với giá trị đặc biệt. Không nhầm nó với việc Content-ID hoặc MIME attachment đã đúng.

Tương tự, charset UTF-8 giúp giữ tiếng Việt nhưng không thay thế escaping HTML và không biến nội dung text thành một HTML an toàn.

## 22. Những assertion không đáng tin cậy cần tránh

### Chỉ verify phương thức gửi

~~~java
verify(sender).send(any(MimeMessage.class));
~~~

Test này có thể pass ngay cả khi PDF không được thêm hoặc CID sai. Hãy capture message và kiểm tra cấu trúc/byte.

### Chỉ so raw Content-Type bằng chuỗi tuyệt đối

~~~java
assertThat(part.getContentType())
        .isEqualTo("application/pdf");
~~~

Header có thể chứa tham số như `name="invoice.pdf"` hoặc charset. Sử dụng:

~~~java
assertThat(part.isMimeType("application/pdf")).isTrue();
~~~

để so kiểu media type chính theo cách Jakarta Mail hỗ trợ.

### Chỉ so raw filename header

~~~java
assertThat(part.getHeader("Content-Disposition")[0])
        .isEqualTo("attachment; filename=invoice.pdf");
~~~

Header có thể có dấu nháy, folding hoặc encoding khác. Hãy test:

~~~java
assertThat(part.getDisposition())
        .isEqualToIgnoringCase(Part.ATTACHMENT);
assertThat(part.getFileName())
        .isEqualTo("invoice.pdf");
~~~

### Giả định thứ tự part là bất biến

~~~java
Multipart multipart = (Multipart) message.getContent();
Part image = multipart.getBodyPart(1);
~~~

Trong mixed-related, part ở vị trí 1 của root có thể là PDF, không phải ảnh. Nếu cần test cấu trúc, duyệt đúng cấp; nếu chỉ cần tìm nội dung, dùng helper recursive.

### Dựa vào `Part.getSize()` để so byte

`Part.getSize()` có thể trả kích thước raw/encoded hoặc giá trị không biết (như `-1`) tùy implementation. Để so nội dung nhị phân, đọc `getInputStream()` và so byte decoded. Với file lớn, có thể stream và so checksum thay vì load toàn bộ vào heap.

### So toàn bộ email source bằng snapshot

MIME boundary, header folding, `Message-ID`, `Date` và encoding có thể thay đổi mà không làm sai chức năng. Đừng biến chi tiết của implementation thành hợp đồng test nếu mục tiêu là kiểm tra attachment/CID.

### Assert một client chắc chắn render đúng từ unit test

Ngay cả khi raw MIME hợp lệ, mail client có thể chặn ảnh, không hỗ trợ HTML/CSS hoặc đưa inline part vào danh sách file. Unit test là nền tảng, còn hiển thị phải được kiểm tra riêng trên các client cần hỗ trợ.

## 23. Lỗi và cách chẩn đoán theo dấu hiệu

| Dấu hiệu | Kiểm tra trong unit test | Hướng xử lý |
|---|---|---|
| Logo hiện thành attachment | Disposition của image, nesting related | Dùng `addInline` và mixed-related phù hợp |
| Logo không hiện trong body | HTML `cid:...` và part Content-ID | Đồng bộ ID giữa template và `addInline` |
| Logo biến mất khi thêm PDF | Vị trí related và mixed group | Dùng mode hỗ trợ nested related + mixed |
| PDF không xuất hiện | `requireFilename`, disposition attachment | Kiểm tra `addAttachment` và branch logic |
| PDF tải về nhưng rỗng | Byte sau `getInputStream` | Kiểm tra resource và khả năng đọc lại stream |
| PDF khác file nguồn | Byte checksum/decoded comparison | Kiểm tra bản snapshot/resource version |
| Hai ảnh bị hoán đổi | Content-ID và byte mỗi part | Test theo ID thay vì theo MIME type đầu tiên |
| Cả text/plain và text/html xuất hiện cùng lúc | Cấu trúc alternative | Dùng `setText(plain, html)` |
| Chỉ thấy plain text | HTML part và alternative | Kiểm tra test MIME, rồi đến client |
| Filename tiếng Việt bị lỗi | `getFileName()` sau round-trip | Kiểm tra Jakarta Mail filename encoding và client |
| Test pass nhưng email client vẫn lỗi | Raw MIME phía nhận | Dùng SMTP sink/client test, xem gateway rewriting |
| AddInline lỗi ở runtime | Multipart flag/mode và resource | Khởi tạo helper với multipart mode phù hợp |
| Test với mock không thấy attachment | Preparator callback chưa được chạy | Dùng Mockito Answer hoặc capture đúng API |
| Lỗi chỉ xuất hiện khi gửi thật | I/O resource, SMTP transport, provider | Kiểm tra round-trip và SMTP integration |

### Phân biệt ba dạng lỗi khác nhau

~~~text
1. Composition error:
   - thêm sai part, resource không đọc được,
     constructor/helper sử dụng sai

2. SMTP submission error:
   - xác thực thất bại, connection timeout,
     provider từ chối recipient/quota

3. Client rendering error:
   - ảnh bị chặn, HTML/CSS không được hỗ trợ,
     cách xử lý inline attachment khác nhau
~~~

Một unit test MIME tốt có thể xác định tầng 1. Nó không tự xử lý các vấn đề của tầng 2 và 3.

## 24. Khi nào cần SMTP sink và kiểm thử hiển thị?

Sau khi unit test pass, có thể thực hiện thêm integration test khi ứng dụng có yêu cầu tương thích email quan trọng:

~~~text
OrderMailService
      |
      v
JavaMailSender
      |
      v
SMTP sink / local mail server
      |
      +-- Raw RFC 822/MIME source
      +-- MIME parts và attachment
      +-- SMTP acceptance
      |
      v
Sau đó: mailbox test trên client thực
~~~

Một SMTP sink như Mailpit hoặc GreenMail có thể giúp kiểm tra message thực sự được gửi qua SMTP mà không phát đến khách hàng. Tùy công cụ, có thể lấy raw source, kiểm tra headers, body part và attachment.

Với yêu cầu client rendering, dùng tài khoản test được quản lý và xác minh:

- Logo hiển thị đúng trong Gmail web/mobile và các client mục tiêu khác.
- PDF có thể tải xuống/mở được.
- Tên file được hiển thị hợp lý.
- Nội dung vẫn đọc được nếu client không tải ảnh.
- HTML và plain text không bị hiển thị đồng thời như hai đoạn body độc lập.

SMTP accepted không đồng nghĩa đã giao đến inbox. DKIM, antispam, mailbox filtering, quota và chính sách client còn ảnh hưởng đến delivery/hiển thị.

### Không dùng SMTP production cho unit test

Unit test không nên phụ thuộc:

- Credential SMTP production.
- DNS/network bên ngoài.
- Người nhận thật.
- Quota hoặc deliverability của nhà cung cấp.

Nếu một bài test về Content-ID cần internet mới chạy được, nó đang kiểm tra quá nhiều tầng cùng lúc. Hãy tách unit, integration và end-to-end test để lỗi có vị trí rõ ràng.

## 25. Bảo mật khi kiểm thử attachment và inline resource

Email có thể chứa tài liệu cá nhân, hóa đơn, ảnh QR, liên kết nhạy cảm hoặc tệp nội bộ. Các bài test về MIME phải chú ý cả **quyền truy cập vào resource** lẫn **rò rỉ dữ liệu qua test artifacts**.

### Không dùng dữ liệu khách hàng thật làm fixture

File `src/test/resources` có thể được commit, đóng gói trong test artifact, sao chép vào cache CI hoặc gửi lên hệ thống báo cáo. Hãy sử dụng:

- PDF/PNG tự tạo chứa dữ liệu giả.
- Địa chỉ `@example.test` hoặc domain dành riêng cho mục đích thử nghiệm.
- Không chứa OTP, access token, account number hoặc PII.
- File đủ nhỏ để kiểm tra được trong môi trường CI.

### Không log byte attachment khi test thất bại

Nếu assertion fail, framework có thể in giá trị actual/expected. Với mảng byte dài, output có thể rất lớn; với dữ liệu thật, có thể lộ thông tin nhạy cảm.

Với fixture nhỏ, `containsExactly` là phù hợp. Với file lớn, nên so:

~~~java
import java.security.MessageDigest;
import java.util.Arrays;

byte[] expectedDigest =
        MessageDigest.getInstance("SHA-256").digest(expectedBytes);
byte[] actualDigest =
        MessageDigest.getInstance("SHA-256").digest(actualBytes);

assertThat(actualDigest).containsExactly(expectedDigest);
~~~

Test dùng hash để không phải hiển thị toàn bộ byte nhị phân khi báo lỗi. Với tệp lớn thực sự, nên tính digest theo stream thay vì load cả hai file vào byte array.

### Không lấy attachment từ đường dẫn do user nhập trực tiếp

Nếu ứng dụng cho phép:

~~~java
helper.addAttachment(
        request.fileName(),
        new FileSystemResource(request.path()));
~~~

với `request.path()` không được kiểm soát, kẻ tấn công có thể tìm cách yêu cầu backend đính kèm file mà nó có quyền đọc, gây lộ dữ liệu. Kiểm thử nghiệp vụ cần xác minh chỉ những resource thuộc user/tenant và được cấp quyền mới được đính kèm.

Việc test `Content-Disposition` đúng **không đủ chứng minh file được phép gửi**. Authorization phải được kiểm tra trước khi dựng MIME.

### MIME type và extension không phải cơ chế xác thực file

`image/png` hoặc `application/pdf` chỉ là nhãn. Nếu nguồn attachment không tin cậy, có thể cần kiểm tra magic bytes, định dạng thực tế, kích thước, chính sách malware scanning và loại file được phép.

Đây là những test thuộc lớp resource ingestion/validation, không thay thế cho test MIME assembly.

## 26. Hiệu năng và giới hạn bộ nhớ của unit test MIME

Các ví dụ dùng `ByteArrayResource` và `readAllBytes()` vì dữ liệu nhỏ, dễ hiểu và dễ kiểm tra. Nhưng không nên copy nguyên cách làm này cho attachment hàng trăm MB:

- Byte array giữ toàn bộ file trong heap.
- Serialize vào `ByteArrayOutputStream` có thể tạo thêm một bản sao raw MIME.
- Parse lại có thể giữ thêm metadata, content cache hoặc luồng xử lý.
- So sánh nhiều bản trong cùng test có thể gây OOM hoặc làm CI chậm.

Một chiến lược phân tầng:

| Quy mô test | Dữ liệu | Cách kiểm tra |
|---|---|---|
| Unit MIME | Vài byte đến vài KB | ByteArrayResource, full decoded-byte comparison |
| Resource test | File fixture nhỏ hợp lệ | ClassPathResource, checksum/byte check |
| Large-file integration | Tệp lớn có giới hạn thực tế | Streaming, checksum, kiểm soát heap/timeouts |
| SMTP end-to-end | Kích thước theo provider policy | SMTP sink/test account, đo size/latency và lỗi |

### Kích thước MIME thường lớn hơn file gốc

Một file được Base64 encode có thể tăng kích thước dữ liệu khoảng một phần ba trước khi cộng thêm line break và MIME headers. Với nhiều attachment, phải tính giới hạn kích thước message của SMTP provider, không chỉ tổng byte file gốc.

Test về giới hạn kích thước nên kiểm tra chính sách ứng dụng trước khi gửi; không cần nhồi một attachment khổng lồ vào unit test để “đoán” provider có chấp nhận hay không.

### Không dựa vào độ trễ tuyệt đối của unit test

Một assertion “MIME phải tạo xong trong 20 ms” có thể flaky trên CI chậm hoặc lúc JVM chưa warmup. Khi cần đánh giá hiệu năng, đo riêng bằng công cụ phù hợp và kiểm soát kích thước nguồn, số phần, bộ nhớ và môi trường chạy.

## 27. Ma trận tình huống kiểm thử đề xuất

Một bộ test có giá trị nên bao phủ cả cấu trúc, dữ liệu và các lỗi dễ xảy ra:

| ID | Tình huống | Assertion quan trọng |
|---|---|---|
| TC-01 | Email chỉ có HTML | Có `text/html`, không tạo attachment ngoài ý muốn |
| TC-02 | Plain + HTML | Có `multipart/alternative` và hai body đúng |
| TC-03 | Một ảnh inline | `image/png`, `inline`, Content-ID khớp HTML |
| TC-04 | Hai ảnh cùng MIME type | Hai Content-ID khác nhau, byte đúng từng ảnh |
| TC-05 | Một PDF attachment | Filename, `attachment`, MIME type và byte đúng |
| TC-06 | Hai PDF khác tên | Mỗi filename ánh xạ đúng byte |
| TC-07 | HTML + inline image + PDF | Related group cho ảnh, mixed cho PDF |
| TC-08 | CID trong HTML sai | Test đối chiếu reference và Content-ID phát hiện thiếu part |
| TC-09 | Hai inline part trùng CID | Test uniqueness báo lỗi |
| TC-10 | Gọi `addInline` như attachment | Assertion disposition/CID thất bại |
| TC-11 | Gọi `addAttachment` như inline | Assertion filename/disposition thất bại |
| TC-12 | Resource classpath không tồn tại | Composer/bước serialization báo lỗi hợp lý |
| TC-13 | InputStreamResource một lần | Test đọc lại/serialize nêu được vấn đề lifecycle |
| TC-14 | Subject và tên file Unicode | Giá trị đã decode còn nguyên sau MIME round-trip |
| TC-15 | Binary content được encode | `getInputStream` trả decoded bytes đúng |
| TC-16 | Service dùng `send(MimeMessage)` | ArgumentCaptor lấy được message đúng |
| TC-17 | Service dùng `send(MimeMessagePreparator)` | Mockito Answer thực thi callback và kiểm tra MIME |
| TC-18 | Attachment không được quyền truy cập | Service từ chối trước khi gửi |
| TC-19 | Tệp quá giới hạn | Application validation từ chối, không submit SMTP |
| TC-20 | Email sau relay | Integration test kiểm tra raw MIME phía server nhận |

Không phải dự án nào cũng cần 20 test riêng. Có thể gom các assertion thuộc cùng một fixture trong một test dễ đọc, miễn thất bại chỉ ra chính xác phần nào sai. Không nên gom toàn bộ các loại email vào một test khổng lồ rồi khó biết nguyên nhân.

### Test nên độc lập với thứ tự chạy

Mỗi test nên tạo `MimeMessage` mới và resource riêng; không chia sẻ một `MimeMessage` mutable giữa các test song song. Cấu trúc MIME, headers và các body part có thể bị thay đổi bởi quá trình compose/serialize; chia sẻ object dễ tạo race condition và test flaky.

### Không chia sẻ byte array mutable không kiểm soát

`ByteArrayResource` có thể giữ tham chiếu đến byte array được cấp. Nếu code khác thay đổi byte sau khi tạo resource, nội dung được serialize sau đó có thể đổi. Với các tác vụ async, hãy cung cấp snapshot bất biến hoặc copy dữ liệu khi cần để tránh trạng thái phụ thuộc timing.

## 28. Quy trình khi một test MIME thất bại

~~~mermaid
flowchart TD
    A[Unit test attachment/CID thất bại] --> B{Message serialize được?}
    B -- Không --> C[Kiểm tra resource, DataHandler, multipart mode]
    B -- Có --> D{Đúng multipart tree?}
    D -- Không --> E[Kiểm tra mode + thứ tự setText/addInline]
    D -- Có --> F{Content-ID khớp HTML?}
    F -- Không --> G[Đồng bộ template và ID]
    F -- Có --> H{Disposition và filename đúng?}
    H -- Không --> I[Kiểm tra addInline và addAttachment]
    H -- Có --> J{Decoded bytes giống nguồn?}
    J -- Không --> K[Kiểm tra stream/readback/encoding]
    J -- Có --> L[Chuyển sang SMTP/client integration nếu lỗi chỉ xuất hiện ở Inbox]
~~~

Quy trình chẩn đoán chi tiết:

1. Kiểm tra code có gọi `setText(...)` trước `addInline(...)` không.
2. Xác định constructor `MimeMessageHelper` dùng multipart mode nào.
3. Xem root subtype và các nhóm related/alternative/mixed.
4. Kiểm tra HTML reference `cid:...`.
5. Tìm part có Content-ID tương ứng, kiểm tra subtype và disposition.
6. Xem filename, media type và disposition của attachment.
7. Parse lại raw MIME, đối chiếu byte decoded với nguồn.
8. Nếu message đúng trong unit test nhưng sai sau SMTP, so raw MIME phía nhận và kiểm tra provider/gateway.
9. Nếu raw MIME phía nhận đúng nhưng UI sai, thử client/phiên bản mục tiêu và chính sách chặn ảnh.

**Không sửa SMTP host, port, username hay password chỉ vì một unit test không tìm thấy Content-ID.** Đó là lỗi cấu trúc MIME phía ứng dụng, thường không liên quan SMTP authentication.

## 29. Câu hỏi thường gặp

**Có cần SMTP server để test attachment không?** Không. Có thể dựng `MimeMessage` trong bộ nhớ, gọi `MimeMessageHelper.addAttachment(...)` rồi duyệt các `Part` để kiểm tra filename, disposition, Content-Type và dữ liệu.

**Có cần SMTP server để test Content-ID không?** Không. Header `Content-ID` và HTML `cid:...` có thể được kiểm tra trước khi gửi.

**Chỉ `verify(sender).send(...)` có đủ không?** Không. Nó chỉ chứng minh service gọi sender; không chứng minh mail có attachment hay inline resource chính xác. Nên capture message và kiểm tra MIME.

**Vì sao phải parse lại sau `writeTo(...)`?** Việc serialize có thể làm rõ lỗi encoding/header/resource chưa xuất hiện khi chỉ đọc object trong bộ nhớ. Parse lại giúp kiểm tra byte MIME mà thư viện tạo ra.

**Vì sao không so `Part.getContentType()` bằng `equals("image/png")`?** Content-Type có thể kèm tham số. `isMimeType("image/png")` phản ánh việc kiểm tra media type phù hợp hơn.

**Content-ID phải có dấu ngoặc nhọn không?** Header MIME thường có `<id>`, còn HTML dùng `cid:id`. Với `MimeMessageHelper.addInline`, truyền ID không chứa `cid:` hoặc dấu ngoặc.

**Content-ID có phải tên file không?** Không. Content-ID là định danh tham chiếu MIME; filename là tên của file được trình bày cho người nhận.

**Part inline có thể có filename không?** Có thể, tùy cách tạo message. Không nên giả định mọi inline resource đều phải có filename null; kiểm tra Content-ID và disposition theo mục đích.

**Attachment có thể có Content-ID không?** Có thể tùy cấu trúc. Vì vậy không kết luận mọi part có Content-ID đều là inline; phải xem Content-Disposition, vị trí và cách HTML tham chiếu.

**Dùng dữ liệu giả vài byte để test ảnh có được không?** Được khi chỉ test MIME assembly và byte preservation. Nhưng dữ liệu đó không chứng minh PNG/PDF hợp lệ để mở hoặc render.

**Tại sao không đọc byte Base64 thô rồi so?** MIME transfer encoding có thể thay đổi. `Part.getInputStream()` cho phép đọc byte decoded để so với nguồn.

**Lỗi từ `MimeMessagePreparator` phải test thế nào?** Khi mock sender, cần thực thi callback preparator trên một MimeMessage thật bằng Mockito Answer; verify callback được truyền chưa đủ.

**Có phải ảnh inline luôn hiển thị trong Gmail/Outlook nếu test pass?** Không. Email client còn có chính sách chặn ảnh, cách render HTML và mức hỗ trợ multipart. Cần client test để xác nhận giao diện.

**Nên test attachment lớn bằng `ByteArrayResource`?** Chỉ với fixture nhỏ. Với tệp lớn, nên test streaming, giới hạn kích thước, checksum và tài nguyên trong một lớp integration test riêng.

**Có nên dùng `InputStreamResource` cho ảnh inline không?** Cần cẩn trọng nếu resource bọc luồng chỉ đọc một lần. Prefer nguồn có thể mở stream mới khi Jakarta Mail cần đọc lại.

**Có phải mọi email HTML đều cần multipart?** Không. Một body `text/html` đơn giản không có inline resource/attachment có thể không cần multipart. Multipart cần thiết khi có nhiều part/attachment hoặc alternative liên quan.

## 30. Nguyên tắc cần nhớ

Trong **Spring Framework Mail**, kiểm thử attachment, inline resource và Content-ID nên tập trung vào **MIME message thật được tạo ra**, không dừng ở việc xác nhận `JavaMailSender.send(...)` đã được gọi.

Ba nguyên tắc cốt lõi:

1. **Kiểm tra đúng part:** attachment theo filename, inline image theo Content-ID, media type và disposition; tránh index cố định khi MIME lồng nhau.
2. **Kiểm tra đúng quan hệ:** HTML phải tham chiếu CID tồn tại; inline resource thuộc related group; attachment độc lập thuộc mixed group khi dùng mode tương ứng.
3. **Kiểm tra dữ liệu không bị thay đổi:** serialize/parse lại message và so byte decoded với fixture gốc, không so Base64/raw MIME snapshot tùy tiện.

Một chiến lược kiểm thử thực tế:

~~~text
Mail composer/service
        |
        v
MimeMessage + MimeMessageHelper
        |
        v
JUnit/Mockito:
   - MIME tree
   - Content-ID ↔ cid: reference
   - Content-Disposition
   - MIME type + filename
   - decoded bytes
        |
        v
MIME round-trip (không SMTP)
        |
        v
SMTP integration khi cần
        |
        v
Client rendering test cho Gmail/Outlook mục tiêu
~~~

**Một email được gửi thành công chưa chắc có nội dung hiển thị đúng.** Unit test MIME giúp bắt lỗi composition sớm, chỉ ra chính xác phần sai và giảm nhu cầu chẩn đoán từ hộp thư thật. Khi kết hợp với kiểm thử SMTP và email client ở lớp phù hợp, ứng dụng có thể kiểm soát tốt hơn việc đính kèm file, nhúng ảnh và tham chiếu Content-ID.
