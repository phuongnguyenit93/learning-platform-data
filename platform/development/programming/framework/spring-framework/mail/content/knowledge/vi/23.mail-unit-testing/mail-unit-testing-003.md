# Kiểm thử nội dung plain text và ký tự Unicode

Trong **Spring Framework Mail**, một email có thể được gửi thành công nhưng vẫn hiển thị sai: tiếng Việt mất dấu, ký tự `₫` biến thành dấu hỏi, emoji bị lỗi, link xác minh bị cắt, hoặc email chỉ có HTML mà không có phần **plain text** cho các mail client đọc văn bản thuần. Những lỗi này thường không xuất hiện trong một unit test chỉ kiểm tra `JavaMailSender.send(...)` đã được gọi.

Để kiểm thử nội dung email có ý nghĩa, cần kiểm tra **hai lớp riêng biệt**:

1. **Nội dung logic do ứng dụng render**: chuỗi `String` plain text có đúng thông tin, Unicode, URL, xuống dòng và format không?
2. **Biểu diễn MIME mà Spring/Jakarta Mail tạo ra**: phần `text/plain` có tồn tại, khai báo charset đúng, nội dung đọc lại sau MIME encoding/decoding có giữ nguyên ký tự Unicode không? Nếu dùng HTML, có cả `text/plain` và `text/html` bên trong `multipart/alternative` không?

Bài học này tập trung vào **kiểm thử đơn vị** trong Spring Mail, sử dụng **JUnit 5, AssertJ, Mockito và Jakarta Mail in-memory**. Không cần kết nối tới một SMTP server thật chỉ để xác minh nội dung plain text hoặc Unicode. Integration test SMTP là lớp kiểm tra khác và được phân biệt rõ ở cuối bài.

## 1. Mục tiêu kiểm thử

Sau bài học, có thể thiết kế test để xác nhận:

- Email giao dịch chứa bản `text/plain` sử dụng được.
- Unicode tiếng Việt như `Đặng, Nguyễn, Ứng dụng, Xác nhận` vẫn nguyên vẹn.
- Ký tự tiền tệ `₫`, dấu câu, chữ có dấu và emoji không bị mất hoặc thay bằng `?`.
- Tiêu đề email chứa Unicode được đọc lại chính xác.
- Plain text giữ nội dung nghiệp vụ: mã đơn hàng, số tiền, thời hạn, URL hành động.
- Plain text không vô tình chứa HTML tags hoặc tham chiếu `cid:` thay vì nội dung có thể đọc.
- Email `multipart/alternative` chứa các bản plain và HTML với cùng dữ kiện.
- MIME parts được khai báo charset phù hợp, thường là UTF-8.
- Các khoảng trắng, đoạn văn và line breaks được thiết kế có chủ đích.
- Kiểm thử không phụ thuộc SMTP credentials, mạng hoặc cách một mail client cụ thể render.

**Một email được gửi thành công không tự chứng minh nội dung đúng.** Ngược lại, test content tốt cũng không chứng minh rằng provider sẽ deliver email vào Inbox.

## 2. Bốn tầng của một email cần phân biệt

Một pipeline thường gặp:

```text
Business data
  |
  v
Template / plain-text renderer
  |
  | Java String, Unicode text
  v
MimeMessageHelper
  |
  | text/plain; charset=UTF-8
  | text/html; charset=UTF-8 (nếu có)
  v
Jakarta Mail MIME serializer
  |
  | Quoted-printable / base64 / headers
  v
JavaMailSender / SMTP
  |
  v
Recipient mail client
```

Kiểm thử đơn vị có thể xác minh **renderer**, **cấu trúc MIME** và **chuỗi được giải mã từ message** mà không gọi SMTP. Còn:
- SMTP AUTH/TLS;
- phản hồi relay;
- provider bounce/deferred;
- inbox placement;
- khả năng hiển thị trên Outlook, Gmail hay thiết bị cụ thể

là các vấn đề của integration, end-to-end hoặc compatibility testing.

### 2.1. Bảng phân định test

| Điều cần kiểm | Unit test phù hợp | Có cần SMTP thật? |
|---|---|---|
| Plain text có mã đơn hàng và URL | Test renderer | Không |
| Dấu tiếng Việt và emoji còn nguyên | Test renderer và MIME decode | Không |
| `text/plain` xuất hiện trong message | Duyệt MIME tree in-memory | Không |
| MIME charset khai báo UTF-8 | Inspect MIME parts | Không |
| Header Subject Unicode đọc lại đúng | `MimeMessage.getSubject()` | Không |
| Spring service gọi sender đúng message | Mockito capture `MimeMessage` | Không |
| Provider nhận SMTP và ký DKIM | Integration test với provider | Có |
| Email vào Inbox và hiển thị trên client | End-to-end / client test | Có |

Không nên dùng mock mà không phân tích message để kết luận rằng nội dung đã được mã hóa đúng.

## 3. Plain text là một phiên bản nội dung độc lập

Một bản plain text tốt không phải một dòng “Hãy bật HTML”. Nó phải đủ để người nhận hiểu và thao tác.

Ví dụ email xác nhận đơn hàng:

```text
Xin chào Nguyễn Thị Ánh,

Đơn hàng ORD-2026-001 của bạn đã được xác nhận.

Tổng tiền: 450.000 ₫
Dự kiến giao: 15/11/2026

Xem chi tiết đơn hàng:
https://shop.example.com/orders/ORD-2026-001

Nếu cần hỗ trợ, hãy trả lời email này.
```

Các thông tin phải còn dùng được khi hoàn toàn không có HTML:
- tên và ngữ cảnh;
- trạng thái;
- mã tham chiếu;
- số tiền và đơn vị tiền;
- ngày tháng;
- liên kết đầy đủ;
- kênh hỗ trợ;
- điều kiện hoặc deadline nếu áp dụng.

Khi HTML có nút:

```html
<a href="https://accounts.example.com/verify?token=example">Xác minh tài khoản</a>
```

plain text phải chứa đường dẫn:

```text
Xác minh tài khoản tại:
https://accounts.example.com/verify?token=example
```

Không chỉ khẳng định văn bản có cụm từ “Xác minh tài khoản” mà bỏ qua URL thật.

## 4. Chuẩn bị dependency kiểm thử

Với Spring Boot và Gradle, một bộ dependency phổ biến:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Starter test thường cung cấp JUnit Jupiter, Mockito và AssertJ qua dependency management của Spring Boot. Tùy phiên bản và build hiện tại, cần xác nhận đúng thư viện test của dự án.

Trong các ví dụ dùng:
- **Spring Framework 6+/Spring Boot 3+**, vì thế import `jakarta.mail.*`, không phải `javax.mail.*` của hệ Jakarta/JavaMail cũ;
- **Java 17+** cho text blocks và records;
- **JUnit Jupiter** cho `@Test`, `@ParameterizedTest`;
- **AssertJ** cho assertion dễ đọc;
- **Mockito** khi cần capture message được service truyền tới `JavaMailSender`.

Không cần thiết lập SMTP host, username hoặc password để kiểm tra một `MimeMessage` được tạo trong bộ nhớ.

## 5. Ưu tiên kiểm thử renderer thuần trước khi kiểm tra MIME

Hãy tách bước render content khỏi bước gửi. Một renderer đơn giản không cần Spring context hay SMTP nên rất nhanh, dễ tái lập và dễ biết lỗi nằm ở đâu.

### 5.1. Model dữ liệu

```java
package com.example.mail;

public record ReceiptData(
    String customerName,
    String orderId,
    String amountText,
    String deliveryDateText,
    String orderUrl
) {}
```

Ở đây các giá trị đã được chuẩn hóa ở lớp nghiệp vụ: số tiền đã định dạng theo locale, ngày giao đã chuyển timezone, URL đã được xây từ nguồn tin cậy. Renderer tập trung vào nội dung.

### 5.2. Renderer plain text

```java
package com.example.mail;

public class ReceiptPlainRenderer {

    public String render(ReceiptData data) {
        return """
            Xin chào %s,

            Đơn hàng %s của bạn đã được xác nhận.

            Tổng tiền: %s
            Dự kiến giao: %s

            Xem chi tiết đơn hàng:
            %s

            Nếu cần hỗ trợ, hãy trả lời email này.
            """.formatted(
                data.customerName(),
                data.orderId(),
                data.amountText(),
                data.deliveryDateText(),
                data.orderUrl()
            );
    }
}
```

Việc dùng Java text block giúp thể hiện các đoạn rõ ràng. Nhưng cần hiểu:
- dấu xuống dòng cuối text block có thể có ý nghĩa;
- incidental indentation được Java xử lý khi biên dịch;
- nội dung đầu vào có thể chứa Unicode;
- renderer không nên vô tình loại bỏ thông tin bằng `trim()` hoặc thay thế ký tự không có chủ đích.

Khi production cần template phức tạp, có thể dùng Thymeleaf/Freemarker hoặc renderer khác. **Đầu ra logic vẫn là chuỗi plain text**, nên cùng chiến lược test áp dụng được.

## 6. Unit test so sánh toàn bộ nội dung mong đợi

Một test đáng tin cậy cho renderer có thể kiểm tra nội dung chuẩn với `isEqualTo`.

```java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class ReceiptPlainRendererTest {

    private final ReceiptPlainRenderer renderer =
        new ReceiptPlainRenderer();

    private ReceiptData sampleData() {
        return new ReceiptData(
            "Nguyễn Thị Ánh",
            "ORD-2026-001",
            "450.000 ₫",
            "15/11/2026",
            "https://shop.example.com/orders/ORD-2026-001"
        );
    }

    @Test
    void rendersCompleteVietnamesePlainText() {
        String actual = renderer.render(sampleData());

        String expected = """
            Xin chào Nguyễn Thị Ánh,

            Đơn hàng ORD-2026-001 của bạn đã được xác nhận.

            Tổng tiền: 450.000 ₫
            Dự kiến giao: 15/11/2026

            Xem chi tiết đơn hàng:
            https://shop.example.com/orders/ORD-2026-001

            Nếu cần hỗ trợ, hãy trả lời email này.
            """;

        assertThat(actual).isEqualTo(expected);
    }
}
```

Test này có ích khi:
- người viết template vô tình đổi số tiền, link, xuống dòng;
- dữ liệu không còn được chèn đúng vị trí;
- mất các ký tự tiếng Việt;
- nội dung nghiệp vụ bị thay bằng một câu thiếu thông tin.

**Không phải mọi email đều cần test so sánh từng ký tự.** Với template thường thay đổi câu chữ, có thể kết hợp test toàn văn cho nội dung ổn định và assertion theo dữ kiện quan trọng để giảm các thay đổi test không cần thiết.

## 7. Unit test theo các điều kiện nghiệp vụ quan trọng

Với email có nội dung được biên tập thường xuyên, test tất cả dấu cách có thể quá cứng. Có thể kiểm tra **hợp đồng nội dung**:

```java
@Test
void plainTextKeepsBusinessFactsAndActionUrl() {
    ReceiptData data = sampleData();

    String plain = renderer.render(data);

    assertThat(plain)
        .contains("Nguyễn Thị Ánh")
        .contains("ORD-2026-001")
        .contains("450.000 ₫")
        .contains("15/11/2026")
        .contains("https://shop.example.com/orders/ORD-2026-001")
        .contains("Nếu cần hỗ trợ");
}
```

Đối với email xác minh hoặc đặt lại mật khẩu, không chỉ assert tên CTA mà phải assert đường dẫn thực tế mà người dùng có thể sao chép.

### 7.1. Không để HTML lọt vào plain text

```java
@Test
void plainTextDoesNotContainHtmlMarkup() {
    String plain = renderer.render(sampleData());

    assertThat(plain)
        .doesNotContain("<html")
        .doesNotContain("<a ")
        .doesNotContain("<table")
        .doesNotContain("cid:");
}
```

Test kiểu substring là lớp bảo vệ đơn giản đối với renderer được kiểm soát, **không phải HTML parser hoàn chỉnh**. Với nội dung đầu vào phức tạp, phải quyết định rõ có cho phép literal angle brackets, đoạn code hay ký tự `<` trong văn bản hay không. Không xây mọi quy tắc “an toàn” chỉ bằng tìm một vài tag.

### 7.2. Tránh placeholder chưa render

Với template engine có placeholder, nội dung gửi ra không được giữ nguyên:

```text
Xin chào `customerName`
Đơn hàng ${orderId}
```

Trong test có thể kiểm tra các placeholder được biết trước, nhưng không nên sử dụng regex quá rộng đến mức coi các ký hiệu hợp lệ trong nội dung của người dùng là lỗi.

## 8. Unicode là gì và vì sao String.length có thể đánh lừa?

Java `String` lưu chuỗi dưới dạng **UTF-16 code units**. Đây là biểu diễn trong JVM, **không phải MIME charset dùng khi truyền email**.

Ví dụ:

```java
String vietnamese = "Đặng Thị Ánh";
String currency = "450.000 ₫";
String emoji = "🚀";
```

Các ký tự tiếng Việt thông dụng có thể nằm trong một code point BMP, trong khi nhiều emoji ở ngoài BMP cần **surrogate pair** trong UTF-16.

### 8.1. UTF-16 code unit, code point và grapheme

Ba khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| UTF-16 code unit | Đơn vị 16-bit mà `String.length()` đếm | Emoji `🚀` thường chiếm 2 units. |
| Unicode code point | Mã Unicode logic | `🚀` là một code point. |
| Grapheme cluster | Đơn vị người dùng thường thấy như một ký tự | Một số emoji ZWJ hoặc chữ + dấu kết hợp có nhiều code points. |

Ví dụ JUnit:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class UnicodeConceptTest {

    @Test
    void countsCodePointsNotOnlyUtf16Units() {
        String rocket = "🚀";

        assertThat(rocket.length()).isEqualTo(2);
        assertThat(
            rocket.codePointCount(0, rocket.length())
        ).isEqualTo(1);
    }
}
```

Không đặt giới hạn nội dung dựa trên `String.length()` và tưởng đó luôn là số “ký tự người dùng nhìn thấy”. Với input validation, cần quy định rõ giới hạn theo bytes, code points hay grapheme clusters.

### 8.2. Unicode trong Java string không có nghĩa MIME tự mặc định UTF-8

Một `String` có thể giữ đúng `Đặng, Ánh, ₫, 🚀`, nhưng khi ghi ra MIME part, thư viện cần lựa chọn **charset** và **Content-Transfer-Encoding** thích hợp. Hãy truyền charset `UTF-8` tường minh cho `MimeMessageHelper` và kiểm tra nội dung sau khi Jakarta Mail decode.

## 9. Test UTF-8 round-trip ở tầng String

Test này kiểm tra logic chuyển byte trong ứng dụng, **chưa phải test MIME**:

```java
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class Utf8TextTest {

    @Test
    void preservesVietnameseCurrencyAndEmojiAsUtf8() {
        String original =
            "Xin chào Nguyễn Thị Ánh — 450.000 ₫ 🎉🚀";

        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
        String decoded =
            new String(bytes, StandardCharsets.UTF_8);

        assertThat(decoded).isEqualTo(original);
    }
}
```

Nếu test này pass, có thể kết luận mã hóa/giải mã UTF-8 tương ứng giữ được chuỗi mẫu. Nhưng **không thể** từ đó khẳng định một `MimeMessage` đã dùng UTF-8. Muốn kiểm chứng MIME phải đọc thực tế phần `Content-Type` và nội dung được decode từ `MimeMessage`.

### 9.1. Vì sao không dùng default charset?

Không nên dùng:

```java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);
```

Ý nghĩa của default charset có thể phụ thuộc môi trường/JDK và cấu hình runtime. Dù nhiều JDK mới dùng UTF-8 mặc định, việc **chỉ định `StandardCharsets.UTF_8`** giúp code và test rõ ràng, ổn định hơn khi dữ liệu cần được trao đổi qua file, network hoặc MIME.

## 10. Chuẩn hóa Unicode NFC và NFD

Một chữ có dấu có thể được biểu diễn bằng nhiều chuỗi code points mà mắt nhìn gần giống nhau.

Ví dụ chữ `ắ`:
- Dạng dựng sẵn: `\u1EAF`.
- Dạng kết hợp: `a\u0306\u0301` (chữ a + dấu breve + dấu sắc).

Trong Java:

```java
import java.text.Normalizer;

String nfcForm = "\u1EAF";
String decomposed = "a\u0306\u0301";

boolean equalAsString = nfcForm.equals(decomposed); // false

String normalized = Normalizer.normalize(
    decomposed,
    Normalizer.Form.NFC
);

boolean equalAfterNfc = nfcForm.equals(normalized); // true
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.text.Normalizer;
import org.junit.jupiter.api.Test;

class UnicodeNormalizationTest {

    @Test
    void supportsCanonicallyEquivalentVietnameseText() {
        String composed = "\u1EAF";
        String decomposed = "a\u0306\u0301";

        assertThat(composed).isNotEqualTo(decomposed);

        assertThat(
            Normalizer.normalize(decomposed, Normalizer.Form.NFC)
        ).isEqualTo(composed);
    }
}
```

### 10.1. Khi nào nên normalize?

Nếu nghiệp vụ yêu cầu so sánh tên hoặc tiêu đề theo nghĩa Unicode canonical equivalence, có thể chuẩn hóa về NFC tại **một điểm đã chọn trong pipeline** rồi áp dụng nhất quán.

Nhưng không phải lúc nào cũng nên normalize tất cả dữ liệu:
- Nội dung được ký hoặc so khớp byte có thể thay đổi khi normalize.
- Token, mã xác minh, password hoặc URL có thể có quy tắc byte riêng.
- Audit cần giữ nguyên dữ liệu gốc trong một số hệ thống.
- Compatibility normalization NFKC/NFKD có thể thay đổi ý nghĩa hiển thị của một số ký tự.

**Chỉ chuẩn hóa khi đó là yêu cầu rõ ràng của hệ thống.** Nếu renderer chủ động normalize input, hãy test quy tắc đó. Nếu renderer phải giữ nguyên input, hãy test rằng chuỗi kết hợp không bị biến đổi ngoài ý muốn.

### 10.2. Đừng dùng Unicode normalization để “sửa” lỗi charset

Một chuỗi đã bị mojibake, ví dụ chữ `Nguyễn` biến thành những ký tự sai vì giải mã nhầm charset, không thể được sửa đáng tin cậy chỉ bằng NFC/NFD. Cần sửa đúng nơi mã hóa hoặc giải mã byte.

## 11. Test plain text trực tiếp trên MimeMessage trong bộ nhớ

Jakarta Mail cho phép tạo `MimeMessage` từ `Session` mà không kết nối mạng.

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.util.Properties;

MimeMessage message = new MimeMessage(
    Session.getInstance(new Properties())
);

MimeMessageHelper helper =
    new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng của Ánh 🎉");

String plainText =
    "Xin chào Nguyễn Thị Ánh,\nTổng tiền: 450.000 ₫ 🚀";

helper.setText(plainText, false);
message.saveChanges();
```

Ở đây:
- `multipart=false` vì chỉ muốn một plain-text message;
- `setText(plainText, false)` tạo content type plain text;
- `saveChanges()` chuẩn bị headers và metadata MIME cần thiết;
- chưa gọi `Transport.send` hay `JavaMailSender.send`, nên **không có SMTP network request**.

### 11.1. Test nội dung đã decode

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.util.Properties;

class PlainMimeMessageTest {

    @Test
    void createsUtf8PlainTextAndPreservesUnicode()
            throws Exception {

        MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties())
        );

        MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");

        String original =
            "Nguyễn Thị Ánh — 450.000 ₫ — 🎉🚀";

        helper.setText(original, false);
        message.saveChanges();

        assertThat(message.isMimeType("text/plain")).isTrue();
        assertThat((String) message.getContent())
            .isEqualTo(original);
    }
}
```

Test này có giá trị vì nó đi qua cách Jakarta Mail biểu diễn content trong MIME rồi **đọc lại nội dung giải mã**.

### 11.2. Kiểm tra charset của Content-Type

```java
import jakarta.mail.internet.ContentType;

ContentType contentType =
    new ContentType(message.getContentType());

assertThat(contentType.getBaseType())
    .isEqualToIgnoringCase("text/plain");

assertThat(contentType.getParameter("charset"))
    .isEqualToIgnoringCase("UTF-8");
```

Tránh assert toàn bộ header `Content-Type` bằng chuỗi nguyên văn vì tên tham số, kiểu quote hoặc thứ tự có thể thay đổi. Parse header theo ngữ nghĩa.

### 11.3. Đừng gán charset bằng tên file nguồn Java

Việc Java source được lưu UTF-8 là tốt, nhưng **không thay thế** việc MIME part khai báo charset phù hợp. Đây là hai lớp khác nhau: source code → Java String, rồi Java String → MIME bytes.

## 12. Vì sao không assert Base64 hoặc quoted-printable cố định?

Khi gửi nội dung Unicode qua MIME, thư viện có thể chọn:

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
```

hoặc:

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64
```

Tùy thư viện, nội dung, cấu hình và các bước serialize, transfer encoding có thể khác. Cả hai đều có thể giữ nội dung Unicode nếu dùng đúng.

**Test bền vững nên so sánh chuỗi đã được decode**, không kiểm tra “email nhất định phải dùng Base64”. Ví dụ:

```java
assertThat((String) message.getContent())
    .isEqualTo("Nguyễn Thị Ánh — 450.000 ₫ 🎉");
```

Có thể assert transfer encoding thuộc tập được phép nếu hệ thống có yêu cầu tương thích cụ thể, nhưng đừng biến chi tiết triển khai không cần thiết thành hợp đồng nội dung.

### 12.1. So sánh ở raw MIME khi thật sự cần

Để quan sát MIME serialization trong test:

```java
import java.io.ByteArrayOutputStream;

ByteArrayOutputStream output = new ByteArrayOutputStream();
message.saveChanges();
message.writeTo(output);

byte[] rawMimeBytes = output.toByteArray();
```

Raw MIME chứa headers, boundary, transfer-encoded bytes và line endings theo tiêu chuẩn email. Dùng nó khi muốn xác minh cấu trúc hoặc phục vụ debug. Không nên lấy `new String(rawMimeBytes, UTF_8)` rồi tìm chuỗi tiếng Việt trực tiếp nếu body đang ở dạng Base64/quoted-printable; **hãy decode bằng Jakarta Mail trước**.

### 12.2. Parse lại MIME bytes

Có thể chứng minh round trip qua serializer và parser:

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;

Session session = Session.getInstance(new Properties());

ByteArrayOutputStream raw = new ByteArrayOutputStream();
message.saveChanges();
message.writeTo(raw);

MimeMessage parsed = new MimeMessage(
    session,
    new ByteArrayInputStream(raw.toByteArray())
);

assertThat(parsed.isMimeType("text/plain")).isTrue();
assertThat((String) parsed.getContent())
    .isEqualTo(original);
```

Đây là test mạnh hơn việc chỉ xem `getContent()` trên message vừa được set nội dung, vì parser phải đọc lại từ bytes của MIME message.

## 13. Plain text trong multipart/alternative: cần duyệt MIME tree

Khi email có cả HTML và plain text:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setText(plainText, htmlText);
```

Spring Mail có thể tạo MIME multipart lồng nhau để hỗ trợ attachment/inline resources, tùy constructor hoặc multipart mode. Do đó **không được giả định `message.getContent()` luôn là `String` hoặc `text/plain` nằm ở part đầu tiên của root multipart**.

Cấu trúc minh họa:

```text
multipart/mixed
└── multipart/related
    └── multipart/alternative
        ├── text/plain; charset=UTF-8
        └── text/html; charset=UTF-8
```

Trong trường hợp không có attachment/inline, thư viện có thể tạo cấu trúc đơn giản hơn. Test cần kiểm tra semantic MIME parts thay vì hardcode số tầng lồng.

### 13.1. Helper tìm part đệ quy

```java
package com.example.mail;

import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.util.ArrayList;
import java.util.List;

public final class MimeTextParts {

    private MimeTextParts() {}

    public static List<Part> find(
            Part root,
            String mimeType) throws Exception {

        List<Part> result = new ArrayList<>();
        visit(root, mimeType, result);
        return result;
    }

    private static void visit(
            Part part,
            String mimeType,
            List<Part> result) throws Exception {

        if (part.isMimeType(mimeType)) {
            result.add(part);
            return;
        }

        Object content = part.getContent();

        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                visit(
                    multipart.getBodyPart(i),
                    mimeType,
                    result
                );
            }
        }
    }
}
```

`Part.isMimeType("text/plain")` nhận diện MIME type mà không cần so khớp đầy đủ charset parameter. Với mục tiêu bài học, helper này đủ để duyệt các `multipart` parts thông thường. Nếu hệ thống dùng `message/rfc822` lồng thư khác, cần quyết định phạm vi duyệt có tính cả message đính kèm hay không để tránh false positive; cũng có thể loại part có disposition `attachment` khi đang tìm **body** chính.

### 13.2. Test có cả plain và HTML

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.util.List;
import java.util.Properties;

class AlternativeMimeTest {

    @Test
    void containsPlainAndHtmlWithoutLosingUnicode()
            throws Exception {

        MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties())
        );

        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        String plain =
            "Xin chào Nguyễn Thị Ánh.\nTổng tiền: 450.000 ₫ 🎉";
        String html =
            "<html><body><p>Xin chào Nguyễn Thị Ánh.</p>"
                + "<p>Tổng tiền: 450.000 ₫ 🎉</p></body></html>";

        helper.setText(plain, html);
        message.saveChanges();

        List<Part> plainParts =
            MimeTextParts.find(message, "text/plain");

        List<Part> htmlParts =
            MimeTextParts.find(message, "text/html");

        assertThat(plainParts).hasSize(1);
        assertThat(htmlParts).hasSize(1);

        assertThat((String) plainParts.get(0).getContent())
            .isEqualTo(plain);

        assertThat((String) htmlParts.get(0).getContent())
            .isEqualTo(html);
    }
}
```

Hai bản có thể khác về layout, nhưng cần có cùng dữ kiện nghiệp vụ. Với email HTML-only, test này sẽ phát hiện thiếu `text/plain`.

### 13.3. Test charset cho từng alternative part

```java
import jakarta.mail.internet.ContentType;

for (Part part : MimeTextParts.find(message, "text/plain")) {
    ContentType type = new ContentType(part.getContentType());

    assertThat(type.getParameter("charset"))
        .isEqualToIgnoringCase("UTF-8");
}

for (Part part : MimeTextParts.find(message, "text/html")) {
    ContentType type = new ContentType(part.getContentType());

    assertThat(type.getParameter("charset"))
        .isEqualToIgnoringCase("UTF-8");
}
```

Nếu có nhiều phần text theo thiết kế, test nên xác định phần nào là body chính, phần nào là attachment hoặc nested forwarded message. Không gộp tất cả rồi chọn ngẫu nhiên một part.

## 14. Kiểm thử service Spring Mail với Mockito

Unit test renderer xác minh chuỗi; MIME test xác minh encoding/cấu trúc. Ở tầng service, cần xác nhận **message đúng được chuyển cho sender**, nhưng vẫn không muốn kết nối SMTP.

Cách làm:
1. Mock `JavaMailSender`.
2. Trả về một `MimeMessage` thật được tạo trong bộ nhớ từ `createMimeMessage()`.
3. Gọi service.
4. Capture `MimeMessage` truyền vào `send(...)`.
5. Kiểm tra MIME parts và nội dung sau decode.

### 14.1. Service gửi một plain-text email

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.charset.StandardCharsets;

public class PlainReceiptMailService {

    private final JavaMailSender sender;
    private final ReceiptPlainRenderer renderer;

    public PlainReceiptMailService(
            JavaMailSender sender,
            ReceiptPlainRenderer renderer) {
        this.sender = sender;
        this.renderer = renderer;
    }

    public void send(
            String recipient,
            ReceiptData data) throws MessagingException {

        MimeMessage mime = sender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
            mime,
            false,
            StandardCharsets.UTF_8.name()
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject(
            "Xác nhận đơn hàng của " + data.customerName()
        );
        helper.setText(renderer.render(data), false);

        sender.send(mime);
    }
}
```

### 14.2. Test Mockito capture

```java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

import java.util.Properties;

class PlainReceiptMailServiceTest {

    @Test
    void sendsUnicodePlainContentWithoutSmtp()
            throws Exception {

        JavaMailSender sender = mock(JavaMailSender.class);
        MimeMessage mime = new MimeMessage(
            Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage()).thenReturn(mime);

        PlainReceiptMailService service =
            new PlainReceiptMailService(
                sender,
                new ReceiptPlainRenderer()
            );

        ReceiptData data = new ReceiptData(
            "Nguyễn Thị Ánh",
            "ORD-2026-001",
            "450.000 ₫",
            "15/11/2026",
            "https://shop.example.com/orders/ORD-2026-001"
        );

        service.send("customer@example.net", data);

        ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender).send(captor.capture());

        MimeMessage sent = captor.getValue();
        sent.saveChanges();

        assertThat(sent.isMimeType("text/plain")).isTrue();
        assertThat(sent.getSubject())
            .isEqualTo("Xác nhận đơn hàng của Nguyễn Thị Ánh");

        String decoded = (String) sent.getContent();

        assertThat(decoded)
            .contains("Nguyễn Thị Ánh")
            .contains("450.000 ₫")
            .contains("ORD-2026-001")
            .contains("https://shop.example.com/orders/ORD-2026-001");
    }
}
```

Mockito mặc định không thực hiện hành động gửi cho `void send(MimeMessage)`. Test vì vậy không gọi SMTP. Sử dụng `MimeMessage` thật thay vì chỉ mock đối tượng MIME cho phép kiểm tra cả thư viện Jakarta Mail xử lý nội dung.

### 14.3. Vì sao không chỉ verify(send)?

Đoạn test quá yếu:

```java
verify(sender).send(any(MimeMessage.class));
```

Nó chỉ chứng minh service đã gọi phương thức. Dù plain text bị bỏ trống, encoding sai, không có URL hoặc tạo HTML-only, test trên vẫn có thể pass.

Nên capture và assert trên message thật hoặc test riêng renderer + MIME builder. Không nhất thiết lặp tất cả nội dung ở mọi tầng; chọn các assertions đại diện cho hợp đồng chức năng của mỗi tầng.

### 14.4. Đừng vô tình gọi send thật trong unit test

Dùng `JavaMailSenderImpl` thực tế trong unit test mà gọi `send` có thể kết nối ra SMTP provider nếu máy có cấu hình mạng/credential. Để test nội dung:
- tạo `MimeMessage` in-memory; hoặc
- mock sender và capture message như trên.

Integration test gọi SMTP test server hoặc sandbox là lớp riêng, có thiết lập tường minh để không phát tán email thật.

## 15. Test Unicode trong Subject và các headers

Nội dung body thường dùng `text/plain; charset=UTF-8`, còn **Subject** là email header có cơ chế mã hóa riêng khi chứa Unicode. Không nên kiểm tra Subject bằng cách giả định raw header luôn là chuỗi UTF-8 literal.

Ví dụ:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(message, false, "UTF-8");

helper.setSubject("Thông báo cho Nguyễn Thị Ánh 🎉");
helper.setText("Nội dung tiếng Việt có dấu.", false);
message.saveChanges();
```

Test ý nghĩa:

```java
assertThat(message.getSubject())
    .isEqualTo("Thông báo cho Nguyễn Thị Ánh 🎉");
```

`getSubject()` trả về giá trị đã được Jakarta Mail giải mã. Còn raw MIME header có thể dùng encoded-word theo chuẩn MIME, ví dụ dạng giống `=?UTF-8?...?=` và cách chia/gấp dòng cụ thể có thể thay đổi.

### 15.1. Tách test decoded value khỏi raw header

Nên test:
- `getSubject()` trả đúng chuỗi Unicode;
- body plain text được decode đúng;
- tên người gửi/địa chỉ được parse đúng nếu có yêu cầu.

Không nên bắt raw Subject phải chứa Unicode literal hoặc một chuỗi Base64 cố định. Điều đó phụ thuộc implementation và encoding choice.

### 15.2. From display name chứa tiếng Việt

```java
helper.setFrom(
    "no-reply@example.com",
    "Cửa hàng Ánh Dương"
);
```

Một unit test có thể parse `InternetAddress` và kiểm tra personal display name đã giải mã theo API thích hợp, thay vì khẳng định raw From header không được mã hóa.

Địa chỉ email thực tế và display name là hai thành phần khác nhau. Unicode trong tên hiển thị không đồng nghĩa SMTP server hỗ trợ địa chỉ local-part Unicode/SMTPUTF8. Nếu ứng dụng cần **email address internationalization**, đó là yêu cầu giao thức riêng và phải được kiểm thử trên SMTP/provider có hỗ trợ phù hợp.

## 16. Kiểm thử line breaks và khoảng trắng

Plain text phụ thuộc mạnh vào:
- dòng trống giữa các đoạn;
- URL ở dòng riêng;
- thụt dòng của danh sách;
- không thừa khoảng trắng làm link hỏng;
- không để đoạn cuối bị nối vào footer;
- xuống dòng hợp lý trên client text-only.

### 16.1. Test format tại renderer

```java
@Test
void keepsReadableParagraphBreaks() {
    String plain = renderer.render(sampleData());

    assertThat(plain)
        .contains("đã được xác nhận.\n\nTổng tiền:")
        .contains("Xem chi tiết đơn hàng:\nhttps://")
        .contains("\n\nNếu cần hỗ trợ");
}
```

Test trên giả định renderer dùng LF là line break logic. Đây là hợp đồng hữu ích ở tầng renderer.

### 16.2. Khi kiểm tra MIME đã serialize, CRLF có thể xuất hiện

Raw email theo định dạng truyền tin dùng dòng kết thúc `CRLF` trong nhiều vị trí. Sau khi parse/serialize, không nên tùy tiện kết luận nội dung sai chỉ vì khác `\n` và `\r\n`.

Nếu yêu cầu nghiệp vụ chỉ quan tâm cấu trúc các dòng, có thể **chuẩn hóa line endings trong test**:

```java
static String normalizeNewlines(String value) {
    return value
        .replace("\r\n", "\n")
        .replace('\r', '\n');
}
```

Rồi so sánh:

```java
assertThat(normalizeNewlines(decodedMimeText))
    .isEqualTo(normalizeNewlines(expectedText));
```

Tuy nhiên, đừng normalize quá mạnh:
- xóa mọi whitespace có thể che mất lỗi ghép từ;
- `trim()` có thể làm mất newline cuối mà contract cần giữ;
- gộp mọi đoạn thành một dòng sẽ làm test không phát hiện nội dung khó đọc.

### 16.3. Không tự chèn MIME boundary vào String

Phần plain text là nội dung logic. Jakarta Mail chịu trách nhiệm MIME boundary, transfer encoding và header. Không tự tạo `--boundary123` hoặc nhúng raw `Content-Type` vào body.

## 17. Test URLs, danh sách và bảng trong text-only email

HTML có thể có nút, bảng và biểu đồ. Trong plain text, thông tin cần được chuyển thành dạng đọc tuyến tính.

Ví dụ HTML:

```html
<table>
  <tr><th>Sản phẩm</th><th>Số lượng</th><th>Giá</th></tr>
  <tr><td>Cà phê</td><td>2</td><td>180.000 ₫</td></tr>
  <tr><td>Trà</td><td>1</td><td>90.000 ₫</td></tr>
</table>
```

Plain text phù hợp hơn:

```text
Chi tiết đơn hàng
-----------------
- Cà phê
  Số lượng: 2
  Giá: 180.000 ₫

- Trà
  Số lượng: 1
  Giá: 90.000 ₫
```

Không chỉ strip HTML tags một cách máy móc, vì nội dung có thể trở thành một chuỗi khó đọc.

### 17.1. Assertion cho URL hành động

```java
@Test
void exposesFullActionUrlInPlainText() {
    String plain = renderer.render(sampleData());

    assertThat(plain).contains(
        "https://shop.example.com/orders/ORD-2026-001"
    );
}
```

Với URL có query string, test nên bảo đảm không bị cắt tại dấu `&` hoặc `?`. Nếu URL có token bí mật, sử dụng **fixture token giả** trong test, không log token thật.

### 17.2. Test các giá trị tiền và ngày giờ

Đừng tính tiền riêng trong HTML renderer và plain renderer. Hãy chuẩn hóa amount/date ở view model rồi dùng chung. Unit test có thể xác nhận cả hai chứa cùng biểu diễn đã chuẩn hóa như `450.000 ₫` và `15/11/2026`.

Nếu bản plain cần hiển thị timezone, kiểm tra rõ `15/11/2026 09:00 ICT` hoặc cách ghi có timezone được hệ thống quy định. Không dựa vào timezone mặc định của máy chạy CI.

### 17.3. Nội dung có ký tự `<`, `>` hoặc dấu `&`

Plain text có thể hợp lệ khi chứa `2 < 3`, `A & B` hoặc đoạn code. Đừng “escape HTML” cả bản plain text rồi biến chúng thành `&lt;` hoặc `&amp;` không cần thiết.

HTML renderer phải escape theo ngữ cảnh của HTML; plain renderer tạo văn bản thuần phù hợp. Hai output **không cần byte-identical** nhưng phải nhất quán về thông tin.

## 18. Parameterized tests cho tiếng Việt và Unicode

Chỉ test một tên có dấu là chưa đại diện cho nhiều dạng dữ liệu. JUnit parameterized tests giúp bao phủ nhiều trường hợp với cùng logic.

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class VietnameseNameRenderingTest {

    private final ReceiptPlainRenderer renderer =
        new ReceiptPlainRenderer();

    @ParameterizedTest
    @ValueSource(strings = {
        "Đặng Thu Hà",
        "Nguyễn Thị Ánh",
        "Trần Đức Thịnh",
        "Phạm Quốc Bảo",
        "Hồ Minh Khuê",
        "Mai 🎉"
    })
    void keepsRecipientName(String customerName) {
        ReceiptData data = new ReceiptData(
            customerName,
            "ORD-001",
            "450.000 ₫",
            "15/11/2026",
            "https://shop.example.com/orders/ORD-001"
        );

        String plain = renderer.render(data);

        assertThat(plain)
            .contains("Xin chào " + customerName + ",");
    }
}
```

Có thể bổ sung input:
- ký tự chữ có dấu dựng sẵn và dạng combining;
- dấu ngoặc kép, apostrophe, dash dài;
- khoảng trắng đầu/cuối theo policy;
- tên trống/null nếu business model cho phép;
- emoji ZWJ sequence;
- ngôn ngữ khác nếu sản phẩm có hỗ trợ quốc tế hóa.

Không nhất thiết gửi email với input không hợp lệ để test rendering. Validate dữ liệu và quyết định fallback nên có các unit test riêng.

### 18.1. Test Unicode code points và surrogate pairs

```java
@Test
void doesNotSplitEmojiSurrogatePairs() {
    String name = "Mai 🚀";

    ReceiptData data = new ReceiptData(
        name,
        "ORD-001",
        "450.000 ₫",
        "15/11/2026",
        "https://shop.example.com/orders/ORD-001"
    );

    String plain = renderer.render(data);

    assertThat(plain).contains(name);
}
```

Không cắt `String` bằng `substring(...)` tại một index ngẫu nhiên rồi mong emoji luôn còn nguyên. Nếu cần truncate theo ký tự, dùng logic dựa trên code points hoặc grapheme segmentation phù hợp mục tiêu.

### 18.2. Test ký tự replacement không xuất hiện ngoài ý muốn

Ký tự `�` (U+FFFD) thường là dấu hiệu từng có lỗi decode, nhưng cũng có thể là một phần của dữ liệu đầu vào hợp lệ trong một số bài toán.

Nếu hợp đồng dữ liệu **không bao giờ cho phép replacement character** trong email đầu ra, có thể assert:

```java
assertThat(plain).doesNotContain("\uFFFD");
```

Đây không phải phương pháp phát hiện mọi lỗi mã hóa. Một chuỗi mojibake có thể không chứa U+FFFD, vì vậy test round-trip và nội dung cụ thể vẫn quan trọng.

## 19. Test email có cả HTML và plain text khi dữ liệu Unicode thay đổi

Giả sử application dùng một view model và hai renderer:

```text
ReceiptData
    |
    +--> plain renderer --> text/plain
    |
    +--> HTML renderer --> text/html
    |
    v
MimeMessageHelper.setText(plain, html)
```

Test nên xác nhận:
- có cả hai MIME representations;
- các giá trị quan trọng xuất hiện ở cả hai;
- Unicode còn nguyên sau decode;
- plain không phụ thuộc nút/link HTML;
- link đích tương đương, nhưng HTML có thể escape `&` thành `&amp;`;
- text-only client vẫn có thể tìm thấy URL đầy đủ.

### 19.1. Không ép bản HTML phải chứa đúng chuỗi plain

HTML có thể là:

```html
<p>Tổng tiền: <strong>450.000 ₫</strong></p>
```

Trong khi plain là:

```text
Tổng tiền: 450.000 ₫
```

So sánh hai chuỗi nguyên văn sẽ fail không có ý nghĩa. Hãy kiểm tra **dữ kiện nghiệp vụ tương đương** bằng các assertion thích hợp cho từng định dạng.

### 19.2. Không cho plain content phụ thuộc ảnh inline

HTML:

```html
<img src="cid:logo" alt="Logo Example Store">
```

Plain:

```text
Example Store
```

Test plain nên chứng minh không có `cid:logo` và vẫn chứa tên tổ chức hoặc thông tin mà ảnh thể hiện. Nếu biểu đồ trong HTML là thông tin nghiệp vụ, bản text nên mô tả số liệu chính, không chỉ nói “xem hình”.

## 20. Các lỗi thường gặp và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Test cần thêm |
|---|---|---|
| Tiếng Việt biến thành dấu hỏi | Sai charset ở bước encode/decode hoặc nguồn dữ liệu đã mất ký tự | UTF-8 round-trip + MimeMessage parse round-trip. |
| Tiêu đề Unicode hiện dạng mã hóa trong assertion | Đang so sánh raw header thay vì decoded Subject | Dùng `getSubject()`. |
| Test passes dù body rỗng | Chỉ verify `send(any())` | Capture message và inspect `getContent()`. |
| Email HTML-only, client text-only không có nội dung | Gọi `setText(html, true)` mà không có plain | Assert tồn tại `text/plain` part. |
| Test MIME nhận `Multipart` thay vì `String` | Dùng `multipart/alternative` hoặc mixed/related | Duyệt MIME tree đệ quy. |
| Test chỉ nhìn raw MIME không tìm thấy `Nguyễn` | Transfer encoding có thể là Base64/QP | Parse/decode bằng Jakarta Mail. |
| NFC và NFD nhìn giống nhưng `equals` false | Khác chuỗi Unicode code points | Test normalization policy. |
| Emoji bị cắt giữa surrogate pair | Truncate bằng UTF-16 index sai | Test code point/grapheme handling. |
| URL hành động biến mất | HTML có button nhưng plain chỉ có nhãn | Assert full action URL trong plain. |
| `&amp;` xuất hiện trong plain text | Tái sử dụng HTML-escaped string | Tách HTML và plain escaping. |
| Số tiền hai bản khác nhau | Hai renderer dùng logic format khác | Dùng chung normalized view model. |
| Test fail vì CRLF vs LF | So sánh sau MIME serialization không xét line endings | Normalize line endings có mục đích. |
| Test phụ thuộc máy developer | Dùng default timezone/locale/charset | Inject locale/clock, explicit UTF-8. |
| CI chạy test gửi email thật | Sử dụng `JavaMailSenderImpl.send` không mock | In-memory MIME + Mockito; test SMTP tách riêng. |
| Ký tự U+FFFD xuất hiện | Input hoặc decode không hợp lệ | Test fixture dữ liệu và điểm decode. |
| MIME charset không đúng dù Java String đẹp | `MimeMessageHelper` không được cấu hình charset tường minh | Test `Content-Type` parameter. |
| Nội dung text có thẻ HTML | Strip tag không đúng hoặc dùng nhầm HTML renderer | Test text contract, link và format. |

## 21. Thiết kế test fixture và tính ổn định trên CI

### 21.1. Đặt fixture ở đâu?

Đối với email ngắn, có thể dùng Java text block ngay trong test. Với nội dung dài hoặc template nhiều ngôn ngữ, lưu fixture trong `src/test/resources` dưới dạng UTF-8:

```text
src/test/resources/mail/
  receipt-vi-plain.txt
  receipt-vi-html.html
  reset-password-plain.txt
```

Đọc tường minh bằng UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String expected = Files.readString(
    Path.of("src/test/resources/mail/receipt-vi-plain.txt"),
    StandardCharsets.UTF_8
);
```

Nếu test chạy trong môi trường khác working directory, nên đọc fixture bằng classpath resource thay vì phụ thuộc đường dẫn relative như trên:

```java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

try (InputStream stream = getClass()
        .getResourceAsStream("/mail/receipt-vi-plain.txt")) {

    if (stream == null) {
        throw new IllegalStateException("Missing test fixture");
    }

    String expected = new String(
        stream.readAllBytes(),
        StandardCharsets.UTF_8
    );
}
```

Nội dung fixture phải có review như code vì golden test có thể pass sai nếu fixture đã bị hỏng encoding.

### 21.2. Test nên deterministic

Tránh:
- phụ thuộc timezone/locale mặc định;
- dùng `Instant.now()` trực tiếp trong renderer;
- random order ID hay token không kiểm soát;
- gửi SMTP thật trong unit tests;
- đọc template từ nguồn network không ổn định;
- dùng charset mặc định cho fixture;
- phụ thuộc thứ tự header MIME không quan trọng;
- giả định một CTE nhất định.

Thay bằng:
- `Clock.fixed(...)` khi format ngày;
- `Locale.forLanguageTag("vi-VN")` khi cần locale Việt;
- `ZoneId.of("Asia/Ho_Chi_Minh")` nếu business scenario cần múi giờ đó;
- ID/token fixture cố định, không nhạy cảm;
- UTF-8 rõ ràng;
- in-memory `MimeMessage` và body-part assertions.

### 21.3. Vì sao tránh assert mọi header byte-for-byte?

Jakarta Mail có thể tự tạo:
- `Message-ID`;
- `Date`;
- MIME boundary;
- `Content-Transfer-Encoding`;
- header folding và encoding khác nhau.

Những chi tiết này có thể thay đổi theo phiên bản thư viện. Nếu mục tiêu test là **nội dung text và Unicode**, chỉ nên assert những gì là hợp đồng của ứng dụng: subject sau decode, MIME type/charset, phần body đã decode, dữ kiện nghiệp vụ và CTA.

## 22. Những điều unit test chưa chứng minh

Kể cả khi toàn bộ unit tests trên pass, vẫn cần những loại kiểm thử khác tùy mức quan trọng:

1. **Integration test SMTP sandbox:** `JavaMailSenderImpl` có thể kết nối, STARTTLS/AUTH hoạt động, SMTP server chấp nhận message.
2. **Provider integration:** có DKIM signing/domain authentication nếu dùng provider ký, các custom header và bounce routing được áp dụng.
3. **End-to-end MIME:** recipient test mailbox nhận đúng content parts/attachment sau khi đi qua relay thực tế.
4. **Mail client compatibility:** Outlook/Gmail/mobile có hiển thị bản plain/HTML như dự định không.
5. **Accessibility:** trình đọc màn hình và text-only workflow có đủ ngữ cảnh không.
6. **Deliverability:** SPF/DKIM/DMARC, complaint, bounce, spam classification và inbox placement.

Cần phân biệt “SMTP accepted” với “recipient delivered”, và “delivered” với “người nhận đã đọc”. Unit test không suy ra những trạng thái đó chỉ từ mock sender.

## 23. Bài tập thực hành

### Bài 1 — Renderer Unicode

Viết `ReceiptPlainRenderer` cho đơn hàng. Test bằng tên `Nguyễn Thị Ánh`, số tiền `450.000 ₫` và link đầy đủ. Assert cả nội dung và line breaks.

### Bài 2 — Mất plain text

Cho service chỉ dùng `helper.setText(html, true)`. Hãy viết MIME unit test phát hiện không có `text/plain`, rồi sửa thành `setText(plain, html)` với multipart helper.

### Bài 3 — MIME decode

Tạo `MimeMessage` text/plain UTF-8 chứa `Đặng, Ứng dụng, ₫, 🎉`. Serialize bằng `writeTo`, parse lại bằng `MimeMessage(Session, InputStream)` rồi so sánh nội dung.

### Bài 4 — Content-Type charset

Kiểm tra `Content-Type` của plain và HTML alternatives bằng `ContentType.getParameter("charset")`. Tránh so khớp raw header nguyên văn.

### Bài 5 — Unicode normalization

Tạo hai chuỗi chữ `ắ` bằng `\u1EAF` và `a\u0306\u0301`. Chứng minh `String.equals` false trước khi normalize và true sau khi `Normalizer.Form.NFC`. Quyết định khi nào nên normalize trong application.

### Bài 6 — Emoji ngoài BMP

Kiểm tra `"🚀".length()` và `codePointCount(...)`. Mô tả vì sao `substring` cắt giữa surrogate pair có thể làm hỏng nội dung.

### Bài 7 — Mockito capture

Mock `JavaMailSender` nhưng trả về `MimeMessage` thật. Capture argument của `send(...)` và assert subject Unicode, MIME type và plain body.

### Bài 8 — Link trong plain text

Một HTML template có nút “Xem hóa đơn”. Viết plain fallback có URL đầy đủ; test để bảo đảm link không bị rút thành nhãn CTA.

### Bài 9 — CRLF versus LF

Test renderer dùng LF; test MIME round-trip có thể gặp line endings khác. Viết helper chuẩn hóa newline **chỉ cho assertion cần thiết**, không dùng `trim()` để che lỗi định dạng.

### Bài 10 — Plain và HTML nhất quán

Tạo hai renderer dùng chung view model. Kiểm tra order ID, số tiền, deadline và URL tương đương trong cả hai, dù cách trình bày khác nhau.

### Bài 11 — Fixture UTF-8

Lưu plain-text fixture tiếng Việt trong `src/test/resources/mail/`. Đọc qua classpath bằng UTF-8 rõ ràng và so sánh kết quả. Đảm bảo không phụ thuộc working directory.

### Bài 12 — Unicode Subject

Tạo subject `Thông báo cho Nguyễn Thị Ánh 🎉`, gọi `saveChanges()` và assert bằng `getSubject()`. Giải thích vì sao raw Subject header có thể không chứa literal Unicode.

### Bài 13 — Không làm mất dấu khi format

Dùng input gồm dấu sắc, huyền, hỏi, ngã, nặng, dấu móc và dấu breve: `Tấn, Huyền, Hỏi, Ngã, Nặng, Ước, Ắt`. Test round-trip qua MIME. Không dùng regex loại bỏ mọi non-ASCII.

### Bài 14 — Kiểm tra trách nhiệm của unit test

Giải thích vì sao test `verify(sender).send(any())` không thể chứng minh email vào Inbox, cũng không thể chứng minh plain body có Unicode đúng.

## 24. Tổng kết

**Kiểm thử nội dung plain text và ký tự Unicode** trong Spring Framework Mail nên bắt đầu từ **renderer thuần** rồi mở rộng sang **MIME message thật trong bộ nhớ**.

Nguyên tắc chính:

1. Kiểm tra plain text như một nội dung độc lập, đầy đủ dữ kiện và URL; không coi nó là phần phụ của HTML.
2. Dùng JUnit/AssertJ để test chuỗi Unicode, số tiền, đường dẫn, đoạn văn và fallback.
3. Dùng `MimeMessageHelper` với charset `UTF-8` và xác minh part `text/plain`/`text/html` theo ngữ nghĩa.
4. Đọc lại bằng `getContent()` hoặc serialize/parse round-trip; **đừng assert raw Base64/quoted-printable cố định**.
5. Với multipart, duyệt **MIME tree đệ quy**, không giả định plain text luôn là nội dung root.
6. Capture `MimeMessage` bằng Mockito để kiểm tra service đã chuẩn bị và chuyển đúng thư cho sender mà **không gọi SMTP thật**.
7. Test Unicode tiếng Việt, `₫`, emoji, NFC/NFD và Subject đã decode; phân biệt UTF-16 units, code points, grapheme clusters.
8. Giữ test deterministic: UTF-8 tường minh, fixture ổn định, locale/timezone/clock có kiểm soát.
9. Tách unit test nội dung khỏi integration test SMTP và end-to-end mail client/deliverability.

Một bộ test tốt không chỉ chứng minh `send(...)` đã được gọi. Nó chứng minh **điều người nhận sẽ đọc trong bản plain text được tạo ra đúng, đủ thông tin và không mất Unicode qua các bước biểu diễn MIME mà ứng dụng kiểm soát**.
