# Kiểm thử MimeMessageHelper với multipart

Trong Spring Framework Mail, `MimeMessageHelper` giúp tạo email có bản text thuần, HTML, ảnh inline và tệp đính kèm. Các lời gọi như `setText(plainText, htmlText)`, `addInline(...)` hay `addAttachment(...)` trông đơn giản, nhưng kết quả là một cấu trúc MIME gồm nhiều phần, mỗi phần có Content-Type, charset, disposition, Content-ID và cách mã hóa riêng. Nếu chỉ kiểm tra rằng method không ném exception, email vẫn có thể thiếu HTML, mất ảnh CID hoặc không chứa attachment mong đợi.

**Kiểm thử đơn vị `MimeMessageHelper` với multipart** là kiểm tra nội dung và cấu trúc của `MimeMessage` ngay trong JVM, không cần SMTP server hay mạng. Bài học này xây bộ test bằng JUnit 5, Jakarta Mail và Spring Mail; hướng dẫn kiểm tra các MIME part sau khi dựng, tránh assertion phụ thuộc boundary động, xác minh attachment bytes và phân biệt unit test với integration test.

## 1. Các thành phần cần hiểu

| Thành phần | Vai trò | Điểm kiểm thử |
| --- | --- | --- |
| `JavaMailSender` | API tạo và gửi message | Có thể mock `createMimeMessage()` và `send(...)` |
| `MimeMessageHelper` | Xây header, nội dung và MIME parts | Chọn multipart mode phù hợp |
| `MimeMessage` | Message chứa header và nội dung | Có thể tạo in-memory bằng Jakarta Mail |
| `Multipart` | Container chứa nhiều `BodyPart` | Có thể lồng nhiều cấp |
| `Part` / `BodyPart` | Một MIME part | MIME type, decoded content, disposition, filename |
| `InputStreamSource` | Cấp bytes cho attachment/inline | Resource phải đọc lại được khi cần |
| `Content-ID` | Liên kết ảnh inline với URI `cid:` | Giá trị trong HTML và header phải tương ứng |
| `Content-Type` | Loại dữ liệu, charset, boundary | Nên parse thay vì so chuỗi nguyên bản |

Một email chỉ có text không bắt buộc có `Multipart`; một email có HTML, ảnh và attachment có thể có vài tầng `Multipart` lồng nhau. Test phải phản ánh cấu trúc dự kiến theo đúng mode.

## 2. Single-part và multipart khác nhau như thế nào?

### Single-part

```java
MimeMessage message = new MimeMessage(
        Session.getInstance(new Properties())
);

MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");
helper.setText("Xin chào, đây là email text.", false);
```

Trong trường hợp này, `message.getContent()` có thể là một `String`. Cast thẳng về `Multipart` sẽ lỗi dù message hợp lệ.

### Multipart alternative

```java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(
        "Đơn hàng của bạn đã được xác nhận.",
        "<p>Đơn hàng của bạn <strong>đã được xác nhận</strong>.</p>"
);
```

Overload `setText(String plainText, String htmlText)` tạo hai biểu diễn cho cùng nội dung, thường nằm trong `multipart/alternative`. Mail client có thể chọn bản text hoặc HTML.

### Multipart với inline và attachment

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setText(plainText, htmlText);
helper.addInline(
        "logo",
        new ByteArrayResource(logoBytes),
        "image/png"
);
helper.addAttachment(
        "report.bin",
        new ByteArrayResource(fileBytes),
        "application/octet-stream"
);
```

Khi đó, các part có thể được lồng qua `multipart/mixed`, `multipart/related` và `multipart/alternative`. Không thể giả định HTML luôn là `getBodyPart(0)` của root.

## 3. Các multipart mode của MimeMessageHelper

| Mode | Cấu trúc | Thích hợp |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Không multipart | Text đơn giản |
| `MULTIPART_MODE_MIXED` | Root `multipart/mixed` | Kết hợp nhiều phần/attachment |
| `MULTIPART_MODE_RELATED` | Root `multipart/related` | Các tài nguyên cùng liên quan tới body |
| `MULTIPART_MODE_MIXED_RELATED` | Root `multipart/mixed` chứa nhánh `multipart/related` | HTML có ảnh inline và attachment |

Constructor `new MimeMessageHelper(message, true, "UTF-8")` dùng chế độ multipart mặc định của Spring. Trong bài test cấu trúc, chỉ rõ mode sẽ giúp người đọc hiểu mục tiêu và giảm phụ thuộc vào giả định không ghi trong code.

Một cây thường gặp:

```text
MimeMessage
  |
  +-- multipart/mixed
        |
        +-- multipart/related
        |     |
        |     +-- multipart/alternative
        |     |     +-- text/plain; charset=UTF-8
        |     |     +-- text/html; charset=UTF-8
        |     |
        |     +-- image/png; Content-ID: <logo>
        |
        +-- application/octet-stream
              Content-Disposition: attachment
              filename=report.bin
```

Sơ đồ mang tính minh họa. Một số chi tiết có thể thay đổi theo mode và phiên bản thư viện; thay vì cố định index của mọi tầng, hãy xác minh sự tồn tại và quan hệ MIME có ý nghĩa.

## 4. Unit test không cần SMTP thật

```text
JUnit 5
   |
   v
Jakarta Mail Session (in-memory)
   |
   v
MimeMessage + MimeMessageHelper
   |
   v
Đọc lại Part / Multipart / header
   |
   v
JUnit assertions
```

`Session.getInstance(new Properties())` không mở kết nối mạng. `new MimeMessage(session)` tạo message tại bộ nhớ. Kiểm thử đơn vị xác nhận dữ liệu đã được **dựng đúng**; nó không chứng minh SMTP chấp nhận message, không kiểm tra TLS hoặc việc Gmail/Outlook render.

Integration test có thể gửi tới GreenMail, Mailpit hoặc MailHog và kiểm tra message mà SMTP test server thực sự nhận. Hai loại test bổ trợ cho nhau, không thay thế nhau.

## 5. Dependency và namespace

Với Spring Boot 3.x/Spring Framework 6+, code thường dùng `jakarta.mail`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Spring Boot quản lý version các thư viện tương thích. Các phiên bản Spring cũ có thể dùng `javax.mail`; không trộn import `javax.mail.*` và `jakarta.mail.*` trong cùng test.

JUnit 5 thuộc bộ test của Spring Boot starter; Mockito và AssertJ cũng thường được cung cấp bởi starter-test. Ví dụ bên dưới sử dụng assertion chuẩn JUnit để ít phụ thuộc cú pháp bổ sung.

## 6. Tạo MimeMessage in-memory

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;

static MimeMessage newMessage() {
    Session session = Session.getInstance(new Properties());
    return new MimeMessage(session);
}
```

Không cần username/password SMTP hay network. Nếu code composer phụ thuộc `JavaMailSender`, có thể mock `createMimeMessage()` hoặc dùng `JavaMailSenderImpl.createMimeMessage()` mà không gọi `send`.

```java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
MimeMessage message = sender.createMimeMessage();
```

`createMimeMessage()` chỉ tạo object; transport SMTP không chạy ở bước này.

## 7. Viết utility duyệt cây MIME

Các part có thể nằm nhiều cấp, vì vậy nên có tiện ích duyệt `Multipart` đệ quy thay vì so sánh vị trí cố định.

```java
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimeTestParts {

    private MimeTestParts() {}

    public static List<Part> flatten(Part root)
            throws MessagingException, IOException {
        List<Part> result = new ArrayList<>();
        visit(root, result);
        return result;
    }

    private static void visit(Part part, List<Part> result)
            throws MessagingException, IOException {
        result.add(part);

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    visit(multipart.getBodyPart(i), result);
                }
            }
        }
    }

    public static boolean contains(
            List<Part> parts, String mimeType
    ) throws MessagingException {
        for (Part part : parts) {
            if (part.isMimeType(mimeType)) {
                return true;
            }
        }
        return false;
    }

    public static Part require(
            List<Part> parts, String mimeType
    ) throws MessagingException {
        for (Part part : parts) {
            if (part.isMimeType(mimeType)) {
                return part;
            }
        }
        throw new AssertionError("Missing MIME type: " + mimeType);
    }

    public static Part requireDisposition(
            List<Part> parts, String disposition
    ) throws MessagingException {
        for (Part part : parts) {
            if (disposition.equalsIgnoreCase(part.getDisposition())) {
                return part;
            }
        }
        throw new AssertionError(
                "Missing disposition: " + disposition);
    }
}
```

### Vì sao dùng vòng lặp?

`Part.isMimeType(...)` và các API khác có thể ném checked `MessagingException`. Dùng vòng lặp tránh vấn đề compile với `Predicate` của Java Stream vốn không khai báo checked exception.

Utility chỉ dành cho message nhỏ do test tạo. Nếu xử lý MIME nhận từ nguồn không tin cậy, cần giới hạn số part, độ sâu, bytes và thời gian parse để tránh tiêu tốn tài nguyên.

## 8. Test bản plain text và HTML cùng tồn tại

```java
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;
import java.util.List;
import java.util.Properties;
import static org.junit.jupiter.api.Assertions.*;

class AlternativeMimeTest {

    @Test
    void containsPlainAndHtml() throws Exception {
        MimeMessage message =
                new MimeMessage(Session.getInstance(new Properties()));

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        String plain = "Xin chào, đơn hàng đã xác nhận.";
        String html = "<p>Xin chào, <strong>đơn hàng"
                + " đã xác nhận</strong>.</p>";

        helper.setFrom("notice@example.org");
        helper.setTo("customer@example.net");
        helper.setSubject("Xác nhận đơn hàng");
        helper.setText(plain, html);

        message.saveChanges();
        List<Part> parts = MimeTestParts.flatten(message);

        assertTrue(MimeTestParts.contains(
                parts, "multipart/alternative"));
        Part textPart = MimeTestParts.require(parts, "text/plain");
        Part htmlPart = MimeTestParts.require(parts, "text/html");

        assertEquals(plain, textPart.getContent());
        assertEquals(html, htmlPart.getContent());
        assertEquals("Xác nhận đơn hàng", message.getSubject());
    }
}
```

Test assert nội dung **đã decode** từ Jakarta Mail, không phụ thuộc raw transfer encoding. Thư viện có thể chọn `quoted-printable` hoặc `base64` tùy dữ liệu; cả hai đều hợp lệ nếu nội dung được tái dựng đúng.

## 9. Test charset UTF-8 đúng cách

Không nên so sánh toàn bộ `Content-Type`:

```java
// Giòn: casing, dấu nháy và thứ tự parameter có thể đổi.
assertEquals("text/html; charset=UTF-8",
        htmlPart.getContentType());
```

Nên parse:

```java
import jakarta.mail.internet.ContentType;
import java.util.Locale;

ContentType htmlType =
        new ContentType(htmlPart.getContentType());

assertEquals("text/html",
        htmlType.getBaseType().toLowerCase(Locale.ROOT));
assertEquals("utf-8",
        htmlType.getParameter("charset")
                .toLowerCase(Locale.ROOT));

ContentType plainType =
        new ContentType(textPart.getContentType());
assertEquals("utf-8",
        plainType.getParameter("charset")
                .toLowerCase(Locale.ROOT));
```

Test có chuỗi `"Xin chào, đơn hàng đã xác nhận."` sẽ phát hiện lỗi hỏng ký tự rõ hơn chỉ kiểm tra header. Một `Content-Type` ghi UTF-8 chưa chứng minh dữ liệu nguồn từng đúng Unicode.

## 10. Test quan hệ parent-child trong alternative

Nếu yêu cầu là `text/plain` và `text/html` cùng nằm trong một `multipart/alternative`:

```java
Part alternativePart =
        MimeTestParts.require(parts, "multipart/alternative");

Multipart alternative =
        (Multipart) alternativePart.getContent();

assertEquals(2, alternative.getCount());
assertTrue(alternative.getBodyPart(0).isMimeType("text/plain"));
assertTrue(alternative.getBodyPart(1).isMimeType("text/html"));
```

Ở cấp `multipart/alternative`, thứ tự bản plain trước HTML có ý nghĩa; nhưng đừng lấy index này áp cho root `multipart/mixed` hoặc `multipart/related`. Những container đó có thể chứa thêm resource/attachment.

## 11. saveChanges() trong test

`MimeMessage.saveChanges()` giúp hoàn thiện những header và trạng thái cần cho serialization. Thường gọi sau khi hoàn tất xây message rồi mới inspect:

```java
MimeMessage message = newMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText("Text", "<p>HTML</p>");
message.saveChanges();

List<Part> parts = MimeTestParts.flatten(message);
```

Lưu ý:

- `saveChanges()` có thể tạo hoặc cập nhật `Message-ID` và header liên quan.
- MIME boundary thường tự sinh; không hard-code giá trị boundary.
- `saveChanges()` không gửi thư và không tạo SMTP result.
- Nếu cần kiểm tra trạng thái trước serialization, hãy test nó riêng với tên giai đoạn rõ ràng.

Với mục tiêu đảm bảo message có thể serialize và parse lại, cần thêm test round-trip `writeTo(...)` rồi tạo `MimeMessage` từ `InputStream`.

## 12. Test multipart với attachment và inline image

Đây là tình huống đầy đủ nhất của bài: một email có plain text, HTML, logo inline qua `cid:` và một attachment dạng nhị phân. Ta muốn chứng minh mỗi phần được dựng với cấu trúc và dữ liệu đúng.

### Chuẩn bị dữ liệu test

Attachment nhị phân có thể dùng một mảng byte cố định, tránh phụ thuộc filesystem:

```java
byte[] attachmentBytes = new byte[] {
        0, 1, 2, 3, 4, 42, 100, 127, (byte) 255
};
```

Với ảnh inline, dùng một file PNG nhỏ trong `src/test/resources/mail/pixel.png`. Đây là fixture test, không chứa dữ liệu người dùng:

```java
byte[] logoBytes;
try (InputStream input = getClass().getResourceAsStream(
        "/mail/pixel.png")) {
    assertNotNull(input, "Missing test resource pixel.png");
    logoBytes = input.readAllBytes();
}
```

Trong test MIME, cần so sánh byte của inline part với file fixture. Việc PNG thật sự render trên mọi mail client là phạm vi integration/visual test khác.

### Test cấu trúc đầy đủ

```java
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.io.InputStream;
import java.util.Arrays;
import java.util.List;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.*;

class MixedRelatedMimeTest {

    @Test
    void buildsInlineImageAndAttachment() throws Exception {
        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties()));

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        String plain = "Xem báo cáo và logo đính kèm.";
        String html = "<p>Xem báo cáo:</p>"
                + "<img src=\"cid:logo\" alt=\"Logo\">";

        byte[] attachmentBytes = new byte[] {
                0, 1, 2, 3, 4, 42, 100, 127, (byte) 255
        };

        byte[] logoBytes;
        try (InputStream input = getClass().getResourceAsStream(
                "/mail/pixel.png")) {
            assertNotNull(input);
            logoBytes = input.readAllBytes();
        }

        helper.setFrom("sender@example.org");
        helper.setTo("recipient@example.net");
        helper.setSubject("Báo cáo kiểm thử MIME");
        helper.setText(plain, html);

        // Thêm inline sau khi đã thiết lập HTML.
        helper.addInline(
                "logo",
                new ByteArrayResource(logoBytes),
                "image/png"
        );
        helper.addAttachment(
                "sample.bin",
                new ByteArrayResource(attachmentBytes),
                "application/octet-stream"
        );

        message.saveChanges();
        List<Part> parts = MimeTestParts.flatten(message);

        assertTrue(MimeTestParts.contains(parts, "multipart/mixed"));
        assertTrue(MimeTestParts.contains(parts, "multipart/related"));
        assertTrue(MimeTestParts.contains(
                parts, "multipart/alternative"));
        assertEquals(plain,
                MimeTestParts.require(parts, "text/plain").getContent());
        assertEquals(html,
                MimeTestParts.require(parts, "text/html").getContent());

        Part inline = MimeTestParts.require(parts, "image/png");
        assertEquals(Part.INLINE, inline.getDisposition());
        assertNotNull(inline.getHeader("Content-ID"));
        assertTrue(Arrays.stream(inline.getHeader("Content-ID"))
                .anyMatch(value -> value.contains("logo")));
        assertArrayEquals(logoBytes,
                inline.getInputStream().readAllBytes());

        Part attachment = MimeTestParts.requireDisposition(
                parts, Part.ATTACHMENT);

        assertTrue(attachment.isMimeType(
                "application/octet-stream"));
        assertEquals("sample.bin", attachment.getFileName());
        assertArrayEquals(attachmentBytes,
                attachment.getInputStream().readAllBytes());
    }
}
```

Test này xác minh **message object** được tạo đúng, không liên quan tới SMTP. Cần có file fixture `pixel.png` trong test resources. Nếu fixture không tồn tại, test thất bại rõ ràng bằng assertion thay vì để lỗi khó hiểu xảy ra khi đọc file.

### Những assertion quan trọng

| Assertion | Điều chứng minh |
| --- | --- |
| Có `multipart/mixed` | Message có nhánh kết hợp nhiều nội dung |
| Có `multipart/related` | Có cấu trúc phục vụ phần nội dung liên quan |
| Có `multipart/alternative` | Có thể chọn text hoặc HTML |
| Plain/HTML đọc lại bằng `getContent()` | Nội dung sau decoding tương ứng model |
| `Part.INLINE` và `Content-ID` | Part inline có đánh dấu và định danh |
| Attachment có disposition và filename | Tệp được đính kèm đúng tên/loại cơ bản |
| `assertArrayEquals` trên `getInputStream()` | Byte attachment/inline không bị thay đổi trong MIME representation |

Không cần assert toàn bộ raw MIME bằng một chuỗi dài, đặc biệt không cần so sánh boundary ngẫu nhiên.

## 13. Kiểm tra Content-ID khớp HTML

Khi thêm ảnh inline:

```java
helper.setText(
        "Nội dung text",
        "<img src=\"cid:logo\" alt=\"Logo\">"
);
helper.addInline(
        "logo",
        new ByteArrayResource(logoBytes),
        "image/png"
);
```

MIME part có header dạng:

```text
Content-ID: <logo>
Content-Disposition: inline
Content-Type: image/png
```

Trong test, có thể kiểm tra:

```java
Part htmlPart = MimeTestParts.require(parts, "text/html");
String htmlContent = (String) htmlPart.getContent();

Part inlinePart = MimeTestParts.require(parts, "image/png");
String[] cidHeaders = inlinePart.getHeader("Content-ID");

assertTrue(htmlContent.contains("cid:logo"));
assertNotNull(cidHeaders);
assertTrue(Arrays.stream(cidHeaders)
        .anyMatch(value -> value.equals("<logo>")));
```

Giá trị `cid:logo` là URI reference trong HTML, còn `Content-ID: <logo>` là header của MIME part. Không truyền cả `cid:` hoặc dấu `< >` vào overload `addInline` nếu code của bạn chỉ cần content ID trần.

Với các message có nhiều inline resources, hãy tạo một tập ID kỳ vọng rồi kiểm tra từng reference có part tương ứng; đừng chỉ kiểm tra tổng số ảnh, vì số lượng đúng vẫn có thể thiếu ID cụ thể.

### Thứ tự setText và addInline

Nên gọi `setText(...)` **trước** `addInline(...)`. Spring Mail documentation lưu ý thứ tự này để mail reader có thể phân giải các inline elements. Test cần giữ đúng cách dựng message mà production sử dụng, tránh viết setup test theo thứ tự khác rồi tưởng lỗi nằm ở Jakarta Mail.

## 14. Kiểm tra attachment bằng byte thật, không bằng Base64 String

MIME có thể mã hóa attachment thành base64. Nhưng `Part.getInputStream()` thường cho đọc lại nội dung đã qua giải mã transfer encoding. Vì vậy, nếu mục tiêu là kiểm tra attachment bytes, hãy so sánh:

```java
byte[] original = new byte[] {
        10, 20, 30, 40, (byte) 200
};

helper.addAttachment(
        "data.bin",
        new ByteArrayResource(original),
        "application/octet-stream"
);

message.saveChanges();
Part filePart = MimeTestParts.requireDisposition(
        MimeTestParts.flatten(message),
        Part.ATTACHMENT
);

assertArrayEquals(
        original,
        filePart.getInputStream().readAllBytes()
);
```

Không nên:

```java
// Dễ phụ thuộc transfer encoding, line wrapping và boundary.
assertTrue(rawMimeString.contains(
        Base64.getEncoder().encodeToString(original)));
```

Raw MIME có thể chia dòng base64, dùng encoding khác hoặc đổi cách serialize. Byte-level decoded comparison ít giòn hơn.

### MIME type không chứng minh định dạng file hợp lệ

`Content-Type: application/pdf` chỉ là khai báo type. Nếu đầu vào là bytes không phải PDF, `MimeMessageHelper` không tự biến chúng thành PDF hợp lệ. Test MIME nên kiểm tra bytes và khai báo type; test xử lý PDF cần xác minh nội dung PDF trong một lớp kiểm thử riêng.

## 15. Kiểm tra Content-Disposition

Disposition thường dùng:

- `Part.ATTACHMENT`: file được đính kèm.
- `Part.INLINE`: part có ý định hiển thị gắn với body.
- `null` hoặc giá trị khác: không nhất thiết lỗi, tùy loại part.

Ví dụ:

```java
Part attachment = MimeTestParts.requireDisposition(
        parts, Part.ATTACHMENT);
assertTrue(attachment.isMimeType("application/octet-stream"));

Part inline = MimeTestParts.require(parts, "image/png");
assertTrue(Part.INLINE.equalsIgnoreCase(
        inline.getDisposition()));
```

Đừng bắt tất cả `text/plain` và `text/html` bắt buộc có `Content-Disposition`. Nhiều body part hợp lệ không có disposition tường minh.

## 16. Kiểm tra số attachment trong message có nhiều phần

Một message có thể chứa logo inline, nhiều PDF và nội dung text. Đếm toàn bộ `BodyPart` không cho biết số attachment:

```text
multipart/mixed
  +-- multipart/related
  |     +-- text/plain
  |     +-- text/html
  |     +-- image/png (inline)
  +-- application/pdf (attachment)
  +-- text/csv (attachment)
```

Hãy đếm theo disposition:

```java
int attachmentCount = 0;
for (Part part : MimeTestParts.flatten(message)) {
    if (Part.ATTACHMENT.equalsIgnoreCase(
            part.getDisposition())) {
        attachmentCount++;
    }
}

assertEquals(2, attachmentCount);
```

Lưu ý test này dựa trên chính sách composer luôn đánh dấu file là attachment. Một email từ nguồn ngoài có thể có filename mà không đặt disposition, nên parser tổng quát cần logic rộng hơn.

## 17. Test MIME round-trip: serialize rồi parse lại

Kiểm thử trực tiếp `MimeMessage` giúp xác định object model. Nhưng nếu mục tiêu là biết message có thể đi qua quá trình serialize, ta có thể ghi bytes vào một buffer **chỉ trong test với dữ liệu giả**, rồi tạo message mới từ bytes ấy.

```java
import jakarta.mail.Session;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.List;
import java.util.Properties;
import static org.junit.jupiter.api.Assertions.*;

void assertMimeRoundTrip(MimeMessage original)
        throws Exception {

    original.saveChanges();

    ByteArrayOutputStream buffer = new ByteArrayOutputStream();
    original.writeTo(buffer);

    Session session = Session.getInstance(new Properties());
    MimeMessage parsed = new MimeMessage(
            session,
            new ByteArrayInputStream(buffer.toByteArray())
    );

    List<Part> parsedParts = MimeTestParts.flatten(parsed);
    assertTrue(MimeTestParts.contains(
            parsedParts, "multipart/alternative"));
    assertTrue(MimeTestParts.contains(
            parsedParts, "text/plain"));
    assertTrue(MimeTestParts.contains(
            parsedParts, "text/html"));
}
```

Đây vẫn là **unit test** vì không có SMTP connection. Nó xác minh Jakarta Mail có thể serialize/parse lại message và các part vẫn tồn tại.

Không gọi `writeTo(System.out)` hoặc dump raw email thật vào log. Với message production, raw MIME có thể chứa Bcc, reset token, attachment và PII; bài test chỉ nên dùng fixture giả.

## 18. Tại sao không nên so sánh raw MIME nguyên chuỗi?

Một assertion dễ giòn:

```java
assertEquals(expectedFullMimeText, actualFullMimeText);
```

Nó có thể thất bại vì:

- MIME boundary được sinh động.
- `Date` thay đổi theo thời gian.
- `Message-ID` có thể thay đổi.
- Header line folding thay đổi.
- Thứ tự các MIME parameter hoặc casing thay đổi.
- Text có thể được encode base64 hoặc quoted-printable.
- Line ending của RFC message khác với string fixture.

Nếu mục tiêu là kết quả có ý nghĩa nghiệp vụ, hãy assert:

```java
assertTrue(MimeTestParts.contains(parts, "text/html"));
assertEquals(expectedHtml,
        MimeTestParts.require(parts, "text/html").getContent());
assertArrayEquals(expectedBytes,
        MimeTestParts.requireDisposition(
                parts, Part.ATTACHMENT)
                .getInputStream().readAllBytes());
```

Chỉ sử dụng golden-file raw MIME khi đang cố tình kiểm thử **serialization format byte-level**. Ngay cả khi ấy, cần kiểm soát timestamp, Message-ID, boundary và version thư viện.

## 19. Test header người gửi, người nhận và Subject

`MimeMessageHelper` không chỉ lo body. Trước khi duyệt multipart, nên kiểm tra các header quan trọng:

```java
helper.setFrom("no-reply@example.org");
helper.setTo("customer@example.net");
helper.setCc("support@example.org");
helper.setSubject("Thông báo kết quả");

message.saveChanges();

assertEquals("Thông báo kết quả", message.getSubject());

InternetAddress[] from =
        (InternetAddress[]) message.getFrom();
assertEquals("no-reply@example.org", from[0].getAddress());

Address[] to = message.getRecipients(
        Message.RecipientType.TO);
assertEquals(1, to.length);
assertEquals("customer@example.net",
        ((InternetAddress) to[0]).getAddress());

Address[] cc = message.getRecipients(
        Message.RecipientType.CC);
assertEquals("support@example.org",
        ((InternetAddress) cc[0]).getAddress());
```

`InternetAddress.getAddress()` giúp kiểm tra địa chỉ tách khỏi display name. Với subject Unicode, `message.getSubject()` trả nội dung đã decode, vì vậy nên assert chuỗi ngữ nghĩa thay vì encoded-word nguyên dạng.

Lưu ý `Bcc` có thể được xử lý khác khi transport gửi message; không nên dùng một bản dump in-memory để suy ra người nhận cuối cùng có thấy hay không thấy header này.

## 20. Test text/html có chứa dữ liệu động

Giả sử một composer render email xác nhận:

```html
<p>Xin chào <span th:text="${customerName}">Khách</span></p>
```

Sau khi render và gọi `helper.setText(plain, html)`, unit test có thể xác minh:

1. Bản text có tên khách hàng.
2. Bản HTML có tên khách hàng được escape phù hợp.
3. Không còn placeholder template.
4. Không làm mất các đường dẫn do backend tạo.
5. Nội dung có charset UTF-8.

Với đầu vào thử `Nguyễn <Admin>`, assertion có thể kiểm tra HTML chứa `&lt;Admin&gt;` thay vì đưa giá trị `<Admin>` thành tag thực. Tuy nhiên, **HTML escaping thuộc về template engine**, không phải trách nhiệm tự động của `MimeMessageHelper`. Nếu truyền HTML đã không escape vào `setText(..., true)`, helper không tự sửa XSS hoặc HTML injection.

Nên tách test template render và test MIME structure; một integration-style composer test có thể kết hợp cả hai để bảo đảm template output đã được đặt đúng vào HTML part.

## 21. Tách MailComposer khỏi thao tác gửi thật

Một thiết kế dễ test là tách trách nhiệm:

- **MailComposer:** từ dữ liệu nghiệp vụ tạo ra một `MimeMessage`.
- **MailSubmissionService:** nhận message và gọi `JavaMailSender.send(...)`.

Ví dụ:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class WelcomeMailComposer {

    private final JavaMailSender sender;

    public WelcomeMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage create(
            String recipient,
            String displayName
    ) throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8");

        helper.setFrom("welcome@example.org");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");
        helper.setText(
                "Xin chào " + displayName,
                "<p>Xin chào <strong>" + displayName
                        + "</strong></p>"
        );
        return message;
    }
}
```

Đây là ví dụ minh họa việc tách composer; trong ứng dụng thật cần **escape hoặc render qua template engine** với dữ liệu người dùng trước khi ghép vào HTML. Test MIME không thay thế kiểm thử output escaping.

Với thiết kế này, unit test có thể quan sát `MimeMessage` trước khi gửi. Nó không cần mở kết nối SMTP và cũng không cần mock tất cả method của `MimeMessageHelper`.

## 22. Test composer với Mockito

Trong test, chỉ mock `JavaMailSender.createMimeMessage()`; object MIME vẫn là Jakarta Mail thật:

```java
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

import java.util.List;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class WelcomeMailComposerTest {

    @Test
    void createsAlternativeContentWithoutSending()
            throws Exception {

        JavaMailSender sender = mock(JavaMailSender.class);
        when(sender.createMimeMessage()).thenAnswer(
                ignored -> new MimeMessage(
                        Session.getInstance(new Properties()))
        );

        WelcomeMailComposer composer =
                new WelcomeMailComposer(sender);

        MimeMessage message = composer.create(
                "recipient@example.net", "Nguyễn An");
        message.saveChanges();

        List<Part> parts = MimeTestParts.flatten(message);

        assertEquals("Chào mừng bạn", message.getSubject());
        assertTrue(MimeTestParts.contains(
                parts, "multipart/alternative"));
        assertEquals(
                "Xin chào Nguyễn An",
                MimeTestParts.require(
                        parts, "text/plain").getContent()
        );

        verify(sender, times(1)).createMimeMessage();
        verify(sender, never()).send(any(MimeMessage.class));
    }
}
```

Ý nghĩa:

- Mockito kiểm tra composer yêu cầu tạo message đúng cách.
- `MimeMessage` là object thật, nên assertions dựa trên cấu trúc MIME thực.
- `send(...)` không được gọi trong composer test.
- Không phải bật Spring application context nếu constructor injection đã đủ.

### Vì sao không mock MimeMessage?

Nếu mock cả `MimeMessage` và `MimeMessageHelper`, bạn chỉ kiểm tra những lời gọi đã được mock mà không biết các part thực tế được tạo ra sao. Với bài kiểm thử multipart, **dùng đối tượng Jakarta Mail thật trong memory** thường giá trị hơn mock object cấp thấp.

## 23. Kiểm thử Service gửi mail ở lớp riêng

Sau khi đã test composer, một unit test khác có thể kiểm tra submission service gọi sender:

```java
public final class MailSubmissionService {

    private final JavaMailSender sender;

    public MailSubmissionService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submit(MimeMessage message) {
        sender.send(message);
    }
}
```

Test:

```java
@Test
void delegatesMimeMessageToSender() {
    JavaMailSender sender = mock(JavaMailSender.class);
    MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties()));

    MailSubmissionService service =
            new MailSubmissionService(sender);

    service.submit(message);

    verify(sender).send(same(message));
}
```

Test này kiểm tra **lời gọi** chứ không kiểm tra SMTP server đã chấp nhận message. Nó nên đi cùng unit test composer và ít nhất một integration test gửi tới SMTP test server khi cần bảo đảm đường đi end-to-end.

## 24. Kiểm thử resource đọc lại được

`addInline(...)` và `addAttachment(...)` nhận các dạng resource/`InputStreamSource`. Trong quy trình gửi hoặc serialize, nguồn dữ liệu có thể phải được mở nhiều lần. Vì vậy, ưu tiên resource đọc lại được.

### ByteArrayResource

```java
byte[] content = new byte[] {10, 20, 30, 40};

helper.addAttachment(
        "data.bin",
        new ByteArrayResource(content),
        "application/octet-stream"
);
```

`ByteArrayResource` tạo `ByteArrayInputStream` mới mỗi lần được yêu cầu; phù hợp cho nội dung nhỏ đã ở memory.

### Cẩn thận với InputStreamResource

`InputStreamResource` thường bọc một stream đã mở, là nguồn **single-use** trong nhiều tình huống. Nếu Jakarta Mail cần đọc lại, có thể bị lỗi hoặc nhận stream đã tiêu thụ.

Không nên dựa vào một test chỉ serialize một lần để kết luận resource chắc chắn phù hợp với quá trình gửi thực tế.

### Một test kiểm tra hai lần serialize

```java
byte[] bytes = new byte[] {1, 2, 3, 4, 5};
MimeMessage message = newMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
helper.setText("File đính kèm");
helper.addAttachment(
        "sample.bin",
        new ByteArrayResource(bytes),
        "application/octet-stream"
);
message.saveChanges();

for (int attempt = 0; attempt < 2; attempt++) {
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    message.writeTo(output);

    MimeMessage parsed = new MimeMessage(
            Session.getInstance(new Properties()),
            new ByteArrayInputStream(output.toByteArray())
    );

    Part attachment = MimeTestParts.requireDisposition(
            MimeTestParts.flatten(parsed),
            Part.ATTACHMENT
    );

    assertArrayEquals(
            bytes,
            attachment.getInputStream().readAllBytes()
    );
}
```

Test này hữu ích cho nguồn byte dạng in-memory. Nó không chứng minh mọi resource thực tế sẽ đọc lại được; nếu ứng dụng gắn file từ object storage, database hoặc filesystem, cần test với loại resource được sử dụng trong production.

## 25. Kiểm thử nhiều attachment

Với hai tệp:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfFixture),
        "application/pdf"
);

helper.addAttachment(
        "items.csv",
        new ByteArrayResource(csvFixture),
        "text/csv"
);
```

Một test nên kiểm tra:

1. Có đúng hai part với disposition `attachment`.
2. Một part có MIME type `application/pdf`, tên `invoice.pdf`.
3. Part còn lại là `text/csv` với tên `items.csv`.
4. Bytes sau khi đọc lại từng part khớp fixture.
5. HTML/text body vẫn tồn tại; thêm attachment không làm mất alternative parts.

Không chọn “attachment thứ hai” chỉ bằng index của root nếu test không quan tâm thứ tự. Hãy tìm bằng disposition + filename hoặc định danh fixture để tránh phụ thuộc vị trí lồng nhau.

### Trùng filename có thể là nghiệp vụ hợp lệ

Hai attachment có thể cùng filename nhưng dữ liệu khác nhau. Nếu application yêu cầu tên file duy nhất, đó là **business validation** nên có test riêng. Jakarta Mail không tự áp đặt quy tắc nghiệp vụ này.

## 26. Kiểm thử multipart mode theo bảng trường hợp

Có thể xây một ma trận:

| Nội dung | Mode | Điều cần assert |
| --- | --- | --- |
| Text đơn | NO | Nội dung là text; không bắt buộc multipart |
| Text + HTML | Multipart | Có `multipart/alternative`, hai body đúng |
| HTML + ảnh inline | RELATED hoặc MIXED_RELATED | Có image part và CID tương ứng |
| Text + attachment | MIXED hoặc MIXED_RELATED | Có attachment disposition và bytes |
| HTML + inline + attachment | MIXED_RELATED | Có nhánh mixed/related/alternative phù hợp |
| Nhiều attachment | MIXED_RELATED | Count, filename, type, bytes đúng |

Không cần viết một test có hàng chục assertion không liên quan. Tách test theo behavior sẽ giúp biết lỗi nằm ở chế độ multipart, body, inline hay attachment.

Ví dụ tên test rõ mục tiêu:

```text
plainTextDoesNotRequireMultipart()
alternativeContainsPlainAndHtml()
htmlUsesUtf8Charset()
mixedRelatedContainsInlineImage()
attachmentRetainsOriginalBytes()
severalAttachmentsKeepTheirMetadata()
serializedMessageCanBeParsedAgain()
```

## 27. Test negative và lỗi khi chuẩn bị MIME

Một số lỗi có thể xảy ra **trước khi SMTP chạy**:

- Địa chỉ email không hợp lệ theo validation của ứng dụng.
- Filename hoặc content ID không hợp lệ theo policy.
- Resource không tồn tại hoặc không thể đọc.
- Template thiếu dữ liệu bắt buộc.
- Không thể dựng MIME part từ nguồn dữ liệu.

Đừng cho rằng tất cả lỗi đều trở thành `MailSendException`; các thao tác dựng `MimeMessage` có thể phát sinh `MessagingException` hoặc Spring có thể bọc lỗi chuẩn bị qua `MailPreparationException` khi dùng `MimeMessagePreparator`.

### Kiểm thử validation của ứng dụng

Nếu service có chính sách chỉ nhận recipient đã được xác thực và attachment dưới 10 MB:

```java
@Test
void rejectsOversizedAttachmentBeforeBuildingMail() {
    byte[] oversized = new byte[10 * 1024 * 1024 + 1];

    assertThrows(
            AttachmentTooLargeException.class,
            () -> mailPolicy.validateSize(oversized.length)
    );
}
```

`AttachmentTooLargeException` và `mailPolicy` ở đây là những thành phần do ứng dụng tự định nghĩa. Test nhằm khẳng định **lớp validation** chặn nội dung không phù hợp, không phải một exception bắt buộc do `MimeMessageHelper` cung cấp.

### Test lỗi resource

Với resource phụ thuộc filesystem hoặc object storage, hãy xác định hệ thống cần:

- Báo lỗi rõ ràng khi không đọc được.
- Không tạo email trống hoặc gửi thiếu tệp mà không thông báo.
- Ghi trạng thái lỗi theo notification.
- Retry hay fail tùy loại lỗi và business policy.

Unit test có thể dùng `InputStreamSource` giả ném `IOException` khi mở stream; nhưng cần nhớ việc đọc resource có thể chỉ xảy ra khi serialize hoặc send, không nhất thiết ngay tại lời gọi `addAttachment(...)`.

## 28. Những gì unit test không thể chứng minh

Một test có thể pass tất cả `MimeMessage` assertions nhưng hệ thống vẫn gặp vấn đề:

| Vấn đề | Vì sao unit test không đủ? | Test bổ sung |
| --- | --- | --- |
| SMTP host/port sai | Không mở kết nối thật | Integration test môi trường thử |
| TLS/STARTTLS lỗi | Không thực hiện handshake | SMTP test có TLS |
| Provider giới hạn size | Không kiểm tra quota server | Integration/configuration test |
| Server từ chối recipient | Không có SMTP RCPT response | SMTP test với rule từ chối |
| Gmail/Outlook render khác | Không chạy mail client | Visual/client compatibility test |
| Email vào spam | Phụ thuộc deliverability và policy | Provider diagnostics |
| DKIM/SPF/DMARC | Phụ thuộc cấu hình domain và relay | Provider/domain tests |
| Email đến Inbox | SMTP acceptance khác delivery | Provider event/mailbox test |
| Gửi trùng sau timeout | Phụ thuộc retry và trạng thái hệ thống | Workflow/idempotency test |

Đừng đặt tên test `emailIsDeliveredSuccessfully()` khi nó chỉ kiểm tra `MimeMessageHelper` đã tạo HTML part.

## 29. Integration test ngắn với SMTP giả lập

Sau unit tests, một integration test có thể:

1. Khởi động SMTP test server như GreenMail hoặc Mailpit.
2. Cấu hình `JavaMailSender` gửi vào host/port của server test.
3. Dựng email bằng composer thật.
4. Gọi `mailSender.send(message)`.
5. Đọc thư mà SMTP test server đã nhận.
6. Parse MIME và xác minh subject, recipient, HTML/text, attachment.

```text
Spring Mail Composer
       |
       v
JavaMailSender.send(...)
       |
       v
SMTP test server
       |
       v
Received MimeMessage
       |
       v
Assert MIME parts + bytes
```

Test này kiểm tra thêm serialization/SMTP submission trong môi trường kiểm thử. Nó vẫn không chứng minh email đã được gửi qua provider production hoặc hiển thị đúng trên mọi mail client.

Không dùng địa chỉ khách hàng thật hoặc SMTP production cho bài test. Với attachment, chỉ dùng fixture không chứa dữ liệu nhạy cảm.

## 30. Các assertion dễ gây flaky

| Assertion không nên dùng | Vì sao dễ sai? | Thay thế |
| --- | --- | --- |
| So sánh toàn raw MIME | Boundary, date, Message-ID thay đổi | Parse MIME rồi assert nội dung |
| So sánh `Content-Type` nguyên chuỗi | Casing, quote, parameter order | `isMimeType` / `ContentType` |
| Giả định HTML ở `root.getBodyPart(0)` | Cây có thể lồng nhiều cấp | Duyệt đệ quy |
| So base64 nguyên chuỗi | Có thể bị line wrap | Đọc decoded `InputStream` |
| So tên boundary cụ thể | Boundary tự sinh | Assert `multipart/*` đúng |
| Đếm tất cả body part là attachment | Bao gồm HTML, text, inline | Đếm disposition |
| Assert `Message-ID` giá trị cố định | Header có thể tự sinh | Assert có mặt nếu yêu cầu |
| `Thread.sleep` chờ gửi mail | Phụ thuộc timing | Future, latch hoặc server test |
| Chỉ verify `send` được gọi | Không kiểm tra message bên trong | Capture/inspect `MimeMessage` |

Khi một version Jakarta Mail mới thay cách encode nhưng decoded content và MIME semantics không đổi, một unit test tốt vẫn nên pass.

## 31. Checklist dành cho một bài test multipart

**Phần setup**

- [ ] Tạo `Session` và `MimeMessage` trong memory.
- [ ] Chọn multipart mode có chủ đích.
- [ ] Dùng recipient, tên và attachment fixture giả.
- [ ] Không gọi SMTP production.

**Phần text/HTML**

- [ ] Có `multipart/alternative` khi dùng plain + HTML.
- [ ] Text và HTML part đúng MIME type.
- [ ] Nội dung sau decoding khớp.
- [ ] Charset/Unicode phù hợp.
- [ ] Template escaping được test riêng.

**Phần inline**

- [ ] HTML chứa URI `cid:...` kỳ vọng.
- [ ] Có part inline với `Content-ID` tương ứng.
- [ ] MIME type và bytes của ảnh đúng.
- [ ] Cấu trúc `multipart/related` phù hợp.

**Phần attachment**

- [ ] Attachment có disposition thích hợp.
- [ ] Filename và Content-Type đúng theo policy.
- [ ] Số attachment đúng.
- [ ] Decoded bytes giống fixture.
- [ ] Resource đọc lại được khi cần.

**Phần độ ổn định**

- [ ] Không so sánh boundary/Message-ID cố định.
- [ ] Không phụ thuộc index của root khi không cần.
- [ ] Có test round-trip nếu muốn kiểm tra serialization.
- [ ] Phân biệt unit test và SMTP integration test.

## 32. Những lỗi thường gặp khi kiểm thử

### Lỗi 1 — Cast root content sang Multipart một cách mù quáng

```java
Multipart multipart = (Multipart) message.getContent();
```

Sai khi test message đơn phần. Hãy xác nhận `message.isMimeType("multipart/*")` trước, hoặc dùng helper duyệt cây có điều kiện.

### Lỗi 2 — Luôn giả định part 0 là HTML

Trong `multipart/alternative`, bản plain thường đứng trước HTML. Trong `mixed/related`, part 0 có thể là một `Multipart` khác. Hãy tìm theo MIME type trong đúng container.

### Lỗi 3 — Dùng InputStreamResource từ stream đã tiêu thụ

Một stream chỉ đọc một lần có thể làm attachment thất bại khi serialize lại. Ưu tiên `ByteArrayResource` hoặc nguồn tạo được stream mới; kiểm tra bằng nhiều lần serialize/đọc trong test khi phù hợp.

### Lỗi 4 — So sánh raw boundary

Boundary thường thay đổi giữa các lần chạy. Test nên assert có `multipart/alternative`, `multipart/related` hoặc `multipart/mixed` chứ không assert `boundary="abc123"`.

### Lỗi 5 — Kiểm tra HTML bằng plain text assertion

`helper.setText(html, true)` tạo HTML-only body, còn `helper.setText(plain, html)` tạo hai biểu diễn. Nếu muốn text fallback, phải dùng đúng overload; test nên yêu cầu cả hai part.

### Lỗi 6 — Thử mail template bằng dữ liệu thật

Không dùng body khách hàng, Bcc hoặc token thật trong test/log. Fixture giả đủ để kiểm tra charset, cấu trúc, encoded header và attachment.

### Lỗi 7 — Cho rằng test thành công nghĩa đã giao thư

Unit test chỉ chứng minh message được dựng đúng. `JavaMailSender.send` thành công cũng chỉ phản ánh SMTP submission theo kết quả transport quan sát được, không bảo đảm Inbox delivery.

## 33. Tình huống luyện tập

### A. Email có HTML nhưng không có bản text

Code dùng `helper.setText("<p>HTML</p>", true)`. Test yêu cầu `multipart/alternative` và `text/plain` nhưng thất bại.

**Giải thích:** overload này chỉ đặt HTML body, không yêu cầu tự tạo plain text fallback. Dùng `setText(plain, html)` trên message multipart nếu nghiệp vụ muốn cả hai.

### B. Test HTML chạy được nhưng inline logo không hiện

Test chỉ xác nhận có part `image/png`, không kiểm tra Content-ID.

**Giải thích:** tồn tại ảnh không đồng nghĩa `cid:logo` trỏ đúng. Test cần đối chiếu giá trị trong HTML với header `Content-ID`, kiểm tra nesting và attachment bytes.

### C. Test attachment thất bại sau lần serialize thứ hai

Code dùng một nguồn stream chỉ đọc được một lần.

**Giải thích:** serialization có thể yêu cầu đọc lại resource. Chuyển sang `ByteArrayResource` hoặc resource mở được stream mới, rồi kiểm tra đọc lại bằng fixture.

### D. Test thất bại sau khi nâng version Jakarta Mail

Content-Type chuyển từ `text/html; charset=UTF-8` sang `text/html; charset="UTF-8"`, nhưng mail vẫn hiển thị đúng.

**Giải thích:** assertion so nguyên chuỗi quá giòn. Dùng `ContentType.getBaseType()` và `getParameter("charset")`.

### E. Test đếm ba body part và kết luận có ba attachment

Message chứa text, HTML và một PDF.

**Giải thích:** body part không đồng nghĩa attachment. Đếm theo disposition và type, trong khi text/HTML là các phần nội dung.

### F. Test verify `sender.send(message)` nhưng production mất HTML

Mockito test chỉ kiểm tra sender được gọi.

**Giải thích:** test đó chưa kiểm tra composer. Dùng `MimeMessage` thật trong unit test, parse `multipart/alternative` và xác minh HTML content.

### G. MIME round-trip pass nhưng Outlook vẫn lỗi

Message serialize và parse lại được bằng Jakarta Mail, nhưng Outlook hiển thị khác.

**Giải thích:** parser round-trip không thay thế compatibility test theo mail client. Gửi fixture tới Outlook test, xem nesting, CID, disposition và HTML rendering.

## 34. Kết luận

Kiểm thử `MimeMessageHelper` với multipart nên tập trung vào **hành vi MIME có ý nghĩa**: có đúng `multipart/alternative` cho plain text và HTML, đúng cấu trúc `mixed/related` cho ảnh inline và attachment, đúng Content-ID, charset, filename/disposition và decoded bytes. Tạo `MimeMessage` bằng Jakarta Mail in-memory giúp các unit test nhanh, không cần SMTP và không phải mock `Multipart` hoặc `BodyPart`.

Để test dễ bảo trì, dùng utility duyệt MIME tree, parse `Content-Type` thay vì so chuỗi raw, không phụ thuộc boundary/Message-ID tự sinh và kiểm tra attachment qua bytes đã decode. Tách `MailComposer` khỏi việc gửi giúp unit test kiểm tra kết quả dựng message, trong khi integration test với SMTP giả lập kiểm tra thêm quá trình gửi/nhận ở transport.

Một unit test multipart thành công chứng minh **message được dựng đúng theo kỳ vọng**, không chứng minh đã gửi thành công hay đến Inbox. Khi giữ ranh giới này rõ ràng, các test vừa phát hiện lỗi cấu trúc trước khi triển khai vừa tránh cảnh báo sai do chi tiết encoding hoặc serialization không quan trọng.
