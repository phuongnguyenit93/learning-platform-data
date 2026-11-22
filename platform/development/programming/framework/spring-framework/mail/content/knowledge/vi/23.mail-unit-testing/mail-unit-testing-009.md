# Kiểm tra template render với dữ liệu biên

Trong ứng dụng **Spring Framework Mail**, email thường được tạo từ một template HTML hoặc plain text, kết hợp với dữ liệu động như tên người nhận, mã đơn hàng, danh sách sản phẩm, số tiền, ngày giờ và đường dẫn thao tác. Một template có thể hiển thị đúng với dữ liệu mẫu nhưng lại lỗi khi tên chứa dấu nháy, danh sách trống, chuỗi rất dài, số tiền bằng 0, thiếu trường bắt buộc hoặc người nhận chọn locale khác.

**Kiểm tra template render với dữ liệu biên** (*boundary-value testing*) là việc cố ý đưa các giá trị ở sát ranh giới hợp lệ, không hợp lệ và khó xử lý vào bước render, rồi xác nhận email được tạo **đúng nội dung, đúng cấu trúc, an toàn và có hành vi lỗi rõ ràng**. Đối tượng kiểm thử chính là lớp biến dữ liệu nghiệp vụ thành subject, HTML và plain-text body; không cần gửi email thật qua SMTP.

Một bài kiểm thử tốt không chỉ hỏi “template có render mà không ném exception không?”. Nó còn kiểm tra dữ liệu có bị mất, bị đổi nghĩa, bị đưa vào HTML không an toàn, làm hỏng URL, bị format sai locale hoặc khiến subject/header không hợp lệ hay không. Đặc biệt, email có thể hiển thị trong những mail client khác nhau; unit test xác nhận kết quả render và MIME structure, còn kiểm thử giao diện trên mail client là một tầng riêng.

Bài học dùng **Thymeleaf**, **JUnit 5**, **AssertJ** và một số ví dụ về `MimeMessageHelper` để minh họa. Các nguyên tắc tương tự áp dụng cho FreeMarker, Mustache và các template engine khác, nhưng cú pháp escape và xử lý giá trị thiếu phải được kiểm tra theo từng engine.

## 1. Xác định đúng ranh giới của unit test

Luồng tổng quát:

```text
Business event / notification command
            |
            v
     Validate input model
            |
            v
  Normalize / format data
     (locale, time zone)
            |
            v
  Subject template renderer
            |
            v
  HTML/plain-text renderer
            |
            v
     RenderedMail object
            |
            v
  MimeMessageHelper builder
            |
            v
  JavaMailSender.send(...)
            |
            v
       SMTP transport
```

Đối với kiểm thử đơn vị về template, nên tập trung từ **input model đến `RenderedMail`**:

- Dữ liệu bắt buộc có hợp lệ không?
- Dữ liệu tùy chọn có được ẩn/hiển thị theo đúng hợp đồng không?
- HTML có escape giá trị không đáng tin cậy không?
- Link có đúng scheme, host và URL format đã phê duyệt không?
- Subject và body có đồng nhất mã đơn hàng, trạng thái và locale không?
- Việc render có phụ thuộc ngầm vào system time zone, default locale hay thứ tự bất định không?
- Template có dễ quan sát lỗi khi thiếu key hoặc missing fragment không?

**Không cần kết nối SMTP để kiểm tra các yêu cầu này.** Nếu test phải thực sự gửi thư mới xác nhận được nội dung, có thể các tầng render và transport đang bị gắn quá chặt.

### Các loại kiểm thử liên quan

| Loại test | Cần kiểm tra | Không nên coi là bằng chứng |
|---|---|---|
| Unit test renderer | Biến model thành subject, HTML, plain text đúng và an toàn | Không chứng minh email được SMTP chấp nhận. |
| Component test template resources | Engine tìm đúng template/fragment, resolve message bundle | Không chứng minh render giống trên mọi client. |
| MIME integration test không mạng | Header, charset, `multipart/alternative`, attachment/CID | Không chứng minh inbox delivery. |
| SMTP integration test | Sender chuyển message cho SMTP test server | Không chứng minh provider thực tế phân phát. |
| Rendering/client preview test | Bố cục trên Gmail, Outlook, mobile, dark mode… | Không thay thế kiểm thử validation/XSS ở dữ liệu nguồn. |

Phần lớn ví dụ sau thuộc hai hàng đầu. Kiểm tra MIME được trình bày ở phần cuối để bảo đảm kết quả render được tích hợp đúng với Spring Mail.

## 2. Định nghĩa hợp đồng dữ liệu của template

Không nên để template đọc trực tiếp một entity chứa hàng chục thuộc tính và quan hệ lazy-loaded. Hãy dùng một **view model riêng cho email**, gồm đúng dữ liệu mà template cần.

Ví dụ email xác nhận đơn hàng:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderMailModel(
        String orderNumber,
        String customerName,
        List<OrderLine> lines,
        BigDecimal total,
        String currencyCode,
        Instant createdAt,
        String detailUrl,
        String optionalNote
) {
}

public record OrderLine(
        String name,
        int quantity,
        BigDecimal price
) {
}
```

Hợp đồng cần ghi rõ từng trường:

| Trường | Bắt buộc? | Dữ liệu biên cần xét |
|---|---|---|
| `orderNumber` | Có | `null`, rỗng, whitespace, Unicode, quá dài, CR/LF. |
| `customerName` | Tùy nghiệp vụ | Rỗng, dấu nháy, `<script>`, emoji, chuỗi dài, RTL. |
| `lines` | Có | `null`, danh sách trống, một phần tử, nhiều phần tử, phần tử `null`. |
| `total` | Có | 0, âm, thập phân dài, giá trị lớn, rounding. |
| `currencyCode` | Có | Mã hợp lệ, không hợp lệ, mismatch với nghiệp vụ. |
| `createdAt` | Có | Gần nửa đêm, DST, ngày nhuận, `null`. |
| `detailUrl` | Có nếu có nút CTA | HTTPS hợp lệ, scheme độc hại, host ngoài allowlist, query đặc biệt. |
| `optionalNote` | Không | `null`, chuỗi rỗng, whitespace, ký tự HTML, chuỗi dài. |

Một yếu tố quan trọng là **định nghĩa hành vi mong đợi trước khi test**. Ví dụ, khi `customerName` rỗng, ứng dụng có thể dùng “Quý khách” hoặc từ chối render; cả hai có thể hợp lý nhưng phải nhất quán. Nếu không có hợp đồng, test chỉ phản ánh hành vi tình cờ của template engine.

### Required và optional phải khác nhau

Giá trị thiếu ở field bắt buộc nên dẫn tới lỗi rõ ràng **trước khi gọi SMTP**. Field optional có thể bỏ đoạn HTML liên quan hoặc có fallback được duyệt.

Ví dụ:

```text
orderNumber = null
    -> Reject: INVALID_ORDER_NUMBER

optionalNote = null
    -> Render without optional-note block

customerName = ""
    -> Either reject or use approved generic greeting
       (choose one policy)
```

Không nên để template tự âm thầm in chuỗi `null`, chuỗi `{0}` hoặc để trống mã đơn hàng quan trọng.

## 3. Tạo fixture có thể dùng lại cho dữ liệu biên

Một test fixture nên cung cấp mẫu hợp lệ tối thiểu rồi cho phép mỗi case thay **một yếu tố**.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public final class OrderMailFixtures {

    private OrderMailFixtures() {}

    public static OrderMailModel validOrder() {
        return new OrderMailModel(
                "ORD-2026-001",
                "Nguyễn An",
                List.of(
                        new OrderLine(
                                "Sách Java",
                                1,
                                new BigDecimal("250000")
                        )
                ),
                new BigDecimal("250000"),
                "VND",
                Instant.parse("2026-11-12T02:15:00Z"),
                "https://shop.example.org/orders/ORD-2026-001",
                null
        );
    }
}
```

Đừng sử dụng dữ liệu ngẫu nhiên hoặc `Instant.now()` trong mọi test. Dữ liệu ổn định giúp khi test lỗi có thể tái hiện chính xác.

### Với record, tạo bản sao để thay một trường

Có thể dùng test-data builder riêng hoặc tạo record mới từ mẫu:

```java
OrderMailModel baseline = OrderMailFixtures.validOrder();

OrderMailModel withBlankName = new OrderMailModel(
        baseline.orderNumber(),
        " ",
        baseline.lines(),
        baseline.total(),
        baseline.currencyCode(),
        baseline.createdAt(),
        baseline.detailUrl(),
        baseline.optionalNote()
);
```

Với model nhiều trường, builder có phương thức `withCustomerName(...)` giúp giảm code lặp và tránh điền nhầm thứ tự. Không dùng `Map.of(...)` khi test `null` vì Java `Map.of` không chấp nhận key/value `null`.

## 4. Template Thymeleaf làm đối tượng kiểm thử

Ví dụ template đặt tại:

```text
src/main/resources/
  mail/
    order-confirmed.html
```

Nội dung:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Xác nhận đơn hàng</title>
</head>
<body>
  <p>
    Xin chào
    <strong data-test="customer-name"
            th:text="${customerName}">Quý khách</strong>
  </p>

  <p>
    Đơn hàng
    <span data-test="order-number"
          th:text="${orderNumber}">ORD-001</span>
    đã được xác nhận.
  </p>

  <ul data-test="order-lines">
    <li class="order-line" th:each="line : ${lines}">
      <span class="line-name" th:text="${line.name}">Sản phẩm</span>
      <span class="line-quantity"
            th:text="${line.quantity}">1</span>
    </li>
  </ul>

  <p>
    Tổng cộng:
    <strong data-test="total"
            th:text="${formattedTotal}">0 đ</strong>
  </p>

  <p data-test="optional-note"
     th:if="${optionalNote != null and !#strings.isEmpty(optionalNote)}"
     th:text="${optionalNote}"></p>

  <a data-test="detail-link"
     th:href="${detailUrl}">
    Xem đơn hàng
  </a>
</body>
</html>
```

Trong Thymeleaf, `th:text` thay nội dung phần tử bằng **text đã được escape cho HTML**. Nó phù hợp khi in dữ liệu không đáng tin cậy như tên người mua hoặc tên sản phẩm. `th:utext` đưa HTML không escaped vào output và chỉ nên dùng với nội dung đã được tin cậy/kiểm soát theo ngữ cảnh.

Các thuộc tính `data-test` giúp test chọn đúng phần tử bằng selector ổn định, thay vì phụ thuộc CSS class phục vụ thiết kế hoặc vị trí thứ tự của DOM.

### Cẩn thận với điều kiện optionalNote

Điều kiện minh họa ẩn note nếu `null` hoặc rỗng. Nếu nghiệp vụ coi chuỗi chỉ có khoảng trắng là trống, nên **trim/normalize ở lớp chuẩn bị model** hoặc dùng quy tắc trong template được test rõ. Chỉ kiểm tra `isEmpty` không đồng nghĩa với kiểm tra `isBlank`.

## 5. Khởi tạo TemplateEngine trong unit test

Có thể cấu hình Thymeleaf trực tiếp mà không cần khởi động toàn bộ Spring Boot context.

```java
import org.junit.jupiter.api.BeforeEach;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

import java.util.Locale;

class OrderMailTemplateTest {

    private TemplateEngine engine;

    @BeforeEach
    void setUp() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();

        resolver.setPrefix("mail/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        engine = new TemplateEngine();
        engine.setTemplateResolver(resolver);
    }

    private String render(
            OrderMailModel order,
            Locale locale,
            String formattedTotal
    ) {
        Context context = new Context(locale);

        context.setVariable(
                "orderNumber", order.orderNumber()
        );
        context.setVariable(
                "customerName", order.customerName()
        );
        context.setVariable("lines", order.lines());
        context.setVariable(
                "formattedTotal", formattedTotal
        );
        context.setVariable(
                "optionalNote", order.optionalNote()
        );
        context.setVariable(
                "detailUrl", order.detailUrl()
        );

        return engine.process("order-confirmed", context);
    }
}
```

Đoạn trên minh họa fixture dùng tài nguyên từ classpath. Khi triển khai test thật, các method kiểm thử được viết trong cùng class hoặc dùng fixture/helper tương ứng.

**Vì sao tắt cache khi test?** Điều này giúp fixture không giữ nội dung template cũ khi test thay đổi resource và giảm hành vi phụ thuộc cache. Trong production có thể bật cache theo chiến lược versioning.

Nếu template thực tế dùng Spring bean expression, message bundle hoặc `SpringTemplateEngine`, test cần khởi tạo engine và dependency tương đương hoặc dùng một component test Spring context. Không nên thay engine production bằng một engine cấu hình khác rồi coi kết quả test là đại diện đầy đủ.

## 6. Kiểm thử trường bắt buộc bằng null, rỗng và whitespace

Nhóm dữ liệu biên đầu tiên gồm:

```text
null
""
" "
"\t"
"\n"
"   \t   "
```

Những giá trị này không hoàn toàn giống nhau. `null` biểu thị không có dữ liệu; chuỗi rỗng tồn tại nhưng không chứa ký tự; chuỗi chỉ có whitespace có thể hiển thị thành khoảng trống dù kỹ thuật vẫn khác rỗng.

Một validator minh họa:

```java
public final class MailModelValidator {

    private MailModelValidator() {}

    public static String requiredSingleLine(
            String value,
            String fieldName
    ) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " is required"
            );
        }

        for (int i = 0; i < value.length();) {
            int codePoint = value.codePointAt(i);

            if (Character.isISOControl(codePoint)) {
                throw new IllegalArgumentException(
                        fieldName + " contains a control character"
                );
            }

            i += Character.charCount(codePoint);
        }

        return value;
    }
}
```

Test tham số:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@NullAndEmptySource
@ValueSource(strings = {" ", " \t ", "\n"})
void rejectsMissingOrderNumber(String value) {
    assertThatThrownBy(() ->
            MailModelValidator.requiredSingleLine(
                    value, "orderNumber"
            )
    ).isInstanceOf(IllegalArgumentException.class);
}
```

Khi dùng `@ValueSource`, cần import assertion từ AssertJ và thiết lập đúng dependency `junit-jupiter-params`. Với model khác, có thể dùng method source để tạo toàn bộ input tương ứng.

### Fail-fast ở đâu?

Validation nên nằm ở ranh giới dựng `MailRenderModel` hoặc renderer service, trước khi sử dụng template. Template engine không phải nơi thích hợp để quyết định một mã đơn hàng `null` có được gửi tới người nhận hay không.

Trong test của renderer, hãy xác nhận **không có thao tác SMTP** khi model không hợp lệ. Nếu renderer độc lập với sender, điều này được đảm bảo về thiết kế; nếu một service orchestrator bao cả hai, dùng mock `JavaMailSender` để verify không gọi `send` khi validation thất bại.

## 7. Kiểm tra dữ liệu optional: không có, có rỗng, có nội dung

Một trường note có thể là:

| Input | Hành vi mong muốn |
|---|---|
| `null` | Không xuất hiện khối note. |
| `""` | Không xuất hiện khối note. |
| `"   "` | Không xuất hiện nếu chính sách trim/normalize whitespace. |
| `"Giao sau 18:00"` | Hiển thị nội dung một lần. |
| `"<b>Quan trọng</b>"` | Hiển thị như văn bản, không biến thành HTML động. |

Kiểm tra cấu trúc DOM với **Jsoup** giúp test không phụ thuộc khoảng trắng và định dạng HTML:

```java
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;

@Test
void hidesOptionalNoteWhenNull() {
    OrderMailModel order = OrderMailFixtures.validOrder();

    String html = render(
            order,
            Locale.forLanguageTag("vi-VN"),
            "250.000 ₫"
    );

    Document document = Jsoup.parse(html);

    assertThat(
            document.select("[data-test=optional-note]")
    ).isEmpty();
}
```

Nếu sản phẩm có fallback cụ thể, test phải khẳng định fallback đó thay vì chỉ kiểm tra phần tử có tồn tại.

### Không để nhãn trống

Một lỗi thực tế là template ẩn nội dung nhưng vẫn còn nhãn:

```text
Ghi chú:
```

Vì vậy, đặt cả label và value trong cùng block condition, rồi test **block biến mất hoàn toàn** khi không có note.

## 8. Kiểm thử ký tự Unicode và dấu tiếng Việt

Template email có thể được đọc bởi người dùng thuộc nhiều ngôn ngữ. Các input cần có:

- Tiếng Việt có dấu: `Nguyễn Thị Ánh`.
- Ký tự ghép và dấu tổ hợp Unicode.
- Emoji nằm ngoài Basic Multilingual Plane: `🎉`.
- CJK: `注文確定`.
- Arabic/Hebrew hoặc nội dung phải-hiển-thị-từ-phải-sang-trái (RTL).
- Ký tự đặc biệt: `&`, `"`, `'`, `<`, `>`.

Ví dụ test:

```java
@Test
void preservesUnicodeInRenderedText() {
    String name = "Nguyễn Ánh 🎉 日本語";
    OrderMailModel order = withCustomerName(
            OrderMailFixtures.validOrder(),
            name
    );

    String html = render(
            order,
            Locale.forLanguageTag("vi-VN"),
            "250.000 ₫"
    );

    Document document = Jsoup.parse(html);

    assertThat(
            document.selectFirst(
                    "[data-test=customer-name]"
            ).text()
    ).isEqualTo(name);
}
```

`withCustomerName(...)` là helper test tạo bản sao record với một field thay đổi. Đây là ví dụ ý tưởng; khi copy vào dự án cần định nghĩa helper/builder đó.

### Phân biệt ký tự và byte

Trong Java, `String.length()` đếm UTF-16 code unit, không nhất thiết bằng số ký tự hiển thị. Emoji hoặc ký tự mở rộng có thể chiếm nhiều code unit.

Khi giới hạn chiều dài dữ liệu hiển thị, cân nhắc:

- Code point count cho chính sách giới hạn ký tự.
- Grapheme cluster nếu cần không cắt dấu kết hợp/emoji sequence.
- UTF-8 byte length cho giới hạn lưu trữ/giao thức.
- Chiều rộng thực tế khi render trên email client, vốn không suy ra chỉ từ độ dài chuỗi.

Không dùng `substring(0, 50)` tùy ý khi có nguy cơ cắt giữa surrogate pair hoặc chuỗi emoji tổ hợp.

## 9. Kiểm thử HTML escaping với dữ liệu không đáng tin cậy

Một biến phổ biến gây lỗi là tên người dùng hoặc tên sản phẩm có HTML-like text:

```text
<script>alert('x')</script>
<img src=x onerror=alert(1)>
A & B < C
"quoted" & 'apostrophe'
```

Nếu template dùng `th:text`, giá trị này phải xuất hiện như văn bản, không trở thành markup thực thi.

Ví dụ:

```java
@Test
void escapesUntrustedCustomerName() {
    String injected =
            "<img src=x onerror=alert(1)>";

    OrderMailModel order = withCustomerName(
            OrderMailFixtures.validOrder(),
            injected
    );

    String html = render(
            order,
            Locale.ENGLISH,
            "VND 250,000"
    );

    Document document = Jsoup.parse(html);

    assertThat(
            document.selectFirst(
                    "[data-test=customer-name]"
            ).text()
    ).isEqualTo(injected);

    assertThat(
            document.select(
                    "[data-test=customer-name] img"
            )
    ).isEmpty();

    assertThat(html).contains("&lt;img");
}
```

Test này kiểm tra cả **giá trị văn bản được giữ nguyên khi parse HTML** và **không tạo phần tử `img` bên trong trường khách hàng**. Nếu chỉ dùng `assertThat(html).contains(injected)`, test có thể vô tình chấp nhận output không được escape.

### th:text và th:utext

Với Thymeleaf:

- `th:text`: escape nội dung theo text context.
- `th:utext`: render nội dung không escape, dễ tạo HTML injection nếu input không tin cậy.

Không dùng `th:utext` chỉ để giữ xuống dòng hoặc định dạng từ user. Nếu nghiệp vụ thực sự cần rich text, hãy định nghĩa chính sách sanitizer với allowlist và test nó như một thành phần riêng.

**HTML escaping không thay thế URL validation, filename validation hoặc subject/header validation.** Mỗi ngữ cảnh output có quy tắc riêng.

## 10. Kiểm thử đường dẫn CTA và link trong email

Một template có thể dùng:

```html
<a th:href="${detailUrl}">Xem đơn hàng</a>
```

Giá trị `detailUrl` là dữ liệu nhạy cảm về mặt điều hướng. Những case nên thử:

| Input | Mong muốn |
|---|---|
| `https://shop.example.org/orders/123` | Chấp nhận. |
| `https://shop.example.org/orders/123?lang=vi&source=mail` | Chấp nhận nếu tạo bằng URL builder và host hợp lệ. |
| `javascript:alert(1)` | Từ chối. |
| `data:text/html,...` | Từ chối. |
| `file:///etc/passwd` | Từ chối. |
| `http://shop.example.org/...` | Từ chối nếu CTA yêu cầu HTTPS. |
| `https://evil.example.net/phishing` | Từ chối nếu ngoài allowlist. |
| `https://shop.example.org.evil.net/...` | Từ chối; không kiểm tra host bằng prefix chuỗi. |
| `""` hoặc `null` | Lỗi hoặc ẩn CTA theo contract. |

### Validator URL minh họa

```java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Set;

public final class MailLinkValidator {

    private static final Set<String> ALLOWED_HOSTS =
            Set.of("shop.example.org");

    public static URI requireApprovedHttpsUrl(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing URL");
        }

        final URI uri;

        try {
            uri = new URI(value);
        } catch (URISyntaxException exception) {
            throw new IllegalArgumentException(
                    "Malformed URL", exception
            );
        }

        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getUserInfo() != null
                || uri.getHost() == null
                || !ALLOWED_HOSTS.contains(
                        uri.getHost().toLowerCase(
                                java.util.Locale.ROOT
                        )
                )) {
            throw new IllegalArgumentException(
                    "URL is not approved"
            );
        }

        return uri;
    }
}
```

Đây là **validator minh họa cho link email**, không phải bộ lọc SSRF toàn diện. Nếu ứng dụng còn dùng URL để server chủ động fetch dữ liệu, cần kiểm soát redirect, DNS resolution, IP đích và egress network riêng.

Trong production, tốt hơn nên **tạo URL từ origin cấu hình đáng tin và ID nghiệp vụ đã encode**, thay vì nhận URL đầy đủ từ client.

### Test link sau render

```java
@Test
void rendersApprovedDetailLink() {
    OrderMailModel order = OrderMailFixtures.validOrder();

    String html = render(
            order,
            Locale.ENGLISH,
            "VND 250,000"
    );

    String href = Jsoup.parse(html)
            .selectFirst("[data-test=detail-link]")
            .attr("href");

    assertThat(href).isEqualTo(order.detailUrl());
}
```

Để test an toàn, còn cần đảm bảo validator chạy **trước** khi renderer nhận `detailUrl` hoặc xây URL trong renderer từ dữ liệu tin cậy.

## 11. Danh sách rỗng, một phần tử và rất nhiều phần tử

Email đơn hàng có thể có số dòng sản phẩm khác nhau:

- `null`: dữ liệu chưa được cung cấp hoặc mapping sai.
- `List.of()`: danh sách trống.
- Một dòng: trường hợp đơn giản nhất.
- Nhiều dòng: kiểm tra lặp và thứ tự.
- Danh sách rất dài: kiểm tra giới hạn nghiệp vụ và kích thước email.
- Một phần tử `null`: cần contract rõ, không chỉ bỏ qua âm thầm.

Một rule khả thi: `lines` bắt buộc không null, nhưng có thể rỗng nếu email dạng “đơn chưa có sản phẩm”; với email xác nhận mua hàng, danh sách trống có thể là lỗi nghiệp vụ. Chọn chính sách đúng rồi test theo đó.

### Ví dụ test danh sách một và nhiều phần tử

```java
@Test
void rendersEveryLineOnceInOrder() {
    OrderMailModel order = withLines(
            OrderMailFixtures.validOrder(),
            List.of(
                    new OrderLine(
                            "Bút bi", 1, new BigDecimal("12000")
                    ),
                    new OrderLine(
                            "Sổ tay", 2, new BigDecimal("50000")
                    )
            )
    );

    String html = render(
            order,
            Locale.forLanguageTag("vi-VN"),
            "112.000 ₫"
    );

    var elements = Jsoup.parse(html)
            .select(".order-line .line-name");

    assertThat(elements).hasSize(2);
    assertThat(elements.get(0).text()).isEqualTo("Bút bi");
    assertThat(elements.get(1).text()).isEqualTo("Sổ tay");
}
```

`withLines(...)` là helper test sao chép record với `lines` mới.

### Khi danh sách rất dài

Không cần in hàng chục nghìn dòng để “chứng minh” template hoạt động. Unit test nên tập trung vào chính sách:

- Có giới hạn item count không?
- Nếu vượt giới hạn thì từ chối, tóm tắt hay liên kết tới trang chi tiết?
- Tổng số được giữ chính xác không?
- Có dòng “và N sản phẩm khác” nếu thiết kế cho phép không?
- Kích thước HTML có giới hạn không?

Không tự động cắt danh sách mà không ghi rõ vì có thể khiến email hóa đơn bỏ mất mục quan trọng. Việc tóm tắt phải theo yêu cầu nghiệp vụ.

## 12. Chuỗi dài và giới hạn kích thước nội dung

Dữ liệu biên về độ dài thường bị bỏ qua:

```text
customerName = "A" repeated 500 times
productName  = one unbroken 2000-character string
note         = 50,000 characters
subject      = a long string with emoji and combining marks
```

Các nguy cơ:

- Subject bị cắt trong giao diện.
- Layout HTML tràn chiều ngang.
- Email body quá lớn, provider từ chối hoặc mail client cắt bớt nội dung.
- Test/snapshot phình to khó đọc.
- Bộ nhớ tăng mạnh khi render nhiều email đồng thời.
- URL hoặc tên sản phẩm không có khoảng trắng không xuống dòng.

Một policy có thể định nghĩa giới hạn theo **field** và theo **rendered output**. Ví dụ:

```java
public static void requireAtMostCodePoints(
        String value,
        int maximum
) {
    int count = value.codePointCount(0, value.length());

    if (count > maximum) {
        throw new IllegalArgumentException(
                "Text length exceeds approved limit"
        );
    }
}
```

Ở ví dụ này, `maximum` là một tham số chính sách, không có một giới hạn chung cho mọi template Spring Mail. Phải kiểm tra `value != null` ở ranh giới bắt buộc hoặc optional trước khi gọi hàm.

### Nếu muốn rút gọn

Nên rút gọn trong lớp chuẩn bị model với quy tắc rõ: giữ mã định danh quan trọng, giới hạn code point/grapheme hợp lý và bổ sung dấu ba chấm nếu được phép. Đừng để template tự cắt dữ liệu tài chính hoặc điều khoản quan trọng.

**Unit test nội dung dài không thay thế visual test**: HTML vẫn có thể đúng về DOM nhưng bị vỡ layout trong một số email client. Với sản phẩm cần hỗ trợ nhiều client, cần thêm render screenshot và kiểm thử hiển thị.

## 13. Số tiền: 0, âm, giá trị lớn và độ chính xác

Số tiền là dữ liệu biên có ảnh hưởng nghiệp vụ cao. Dùng `BigDecimal` thay vì phép tính tiền bằng `double`.

Các case:

| Input | Điều cần xác nhận |
|---|---|
| `BigDecimal.ZERO` | Định dạng 0 theo currency, không biến mất do điều kiện truthy/falsey. |
| `-1.00` | Bị từ chối nếu nghiệp vụ không cho âm hoặc hiển thị đúng cho refund. |
| `0.01` | Không bị làm tròn thành 0 sai chính sách. |
| `999999999999.99` | Không overflow, không mất chữ số. |
| `1.005` | Rounding theo quy định; không tự suy đoán HALF_UP cho mọi loại tiền. |
| `null` | Báo lỗi nếu `total` là required. |
| Currency khác | Ký hiệu, số chữ số thập phân và vị trí phù hợp. |

Ví dụ format ở lớp chuẩn bị:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public static String formatMoney(
        BigDecimal value,
        String currencyCode,
        Locale locale
) {
    if (value == null) {
        throw new IllegalArgumentException("Missing amount");
    }

    Currency currency = Currency.getInstance(currencyCode);

    NumberFormat formatter = NumberFormat.getCurrencyInstance(
            locale
    );
    formatter.setCurrency(currency);

    return formatter.format(value);
}
```

Ví dụ trình bày cách tách format khỏi template. Trong production, cần xác định số chữ số thập phân và rounding theo **currency và chính sách nghiệp vụ**, không mặc định format hiển thị đủ để thay thế phép tính kế toán.

### Không assert một dấu phân cách tùy ý cho mọi locale

Với locale khác nhau, cùng số tiền có thể được in như:

```text
250.000 ₫
VND 250,000
¥250,000
```

Chuỗi thực tế phụ thuộc locale, currency, version JDK/CLDR và cấu hình. Test nên cố định môi trường hoặc kiểm tra semantic hợp đồng đã được chốt. Nếu sản phẩm yêu cầu format pixel-perfect, dùng formatter cấu hình rõ và snapshot có version thay vì phụ thuộc ngầm default locale của máy CI.

## 14. Ngày giờ: time zone, DST và thời điểm biên

Email nhắc lịch hẹn hoặc xác nhận giao dịch thường có thời gian. Những lỗi khó gặp ở dữ liệu mẫu nhưng xuất hiện tại ranh giới:

- Một `Instant` gần nửa đêm UTC nhưng là ngày khác tại Việt Nam.
- Chuyển đổi giờ mùa hè (DST) tại một time zone có áp dụng.
- Ngày nhuận 29/02.
- Cuối tháng, cuối năm.
- Giờ địa phương không tồn tại hoặc lặp lại khi DST chuyển.
- `createdAt=null` trong một template bắt buộc hiển thị ngày.

**Locale và time zone là hai thứ khác nhau.** Một khách hàng chọn tiếng Anh không có nghĩa họ ở London; một giao dịch bằng USD không chứng minh time zone là Mỹ.

Ví dụ:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public static String formatOrderTime(
        Instant instant,
        Locale locale,
        ZoneId zone
) {
    return DateTimeFormatter
            .ofLocalizedDateTime(FormatStyle.MEDIUM)
            .withLocale(locale)
            .withZone(zone)
            .format(instant);
}
```

Test nên dùng `Instant` cố định và `ZoneId` rõ ràng:

```java
@Test
void formatsNearMidnightInRecipientTimeZone() {
    Instant instant =
            Instant.parse("2026-11-12T23:45:00Z");

    String result = formatOrderTime(
            instant,
            Locale.forLanguageTag("vi-VN"),
            ZoneId.of("Asia/Ho_Chi_Minh")
    );

    // Giá trị UTC chuyển sang ngày 13/11 tại Việt Nam.
    assertThat(
            instant.atZone(
                    ZoneId.of("Asia/Ho_Chi_Minh")
            ).getDayOfMonth()
    ).isEqualTo(13);

    assertThat(result).isNotBlank();
}
```

Test này xác nhận ranh giới ngày theo zone và kết quả format không trống. Nếu yêu cầu văn bản chính xác đến từng dấu, có thể cố định formatter pattern/locale và assert kết quả đầy đủ phù hợp.

### Tránh system clock trong renderer

Không nên render “Ngày hôm nay” bằng cách gọi `LocalDate.now()` ở nhiều nơi trong template. Unit test lúc 23:59 có thể khác lúc 00:01.

Nếu cần current time, truyền `Clock` hoặc timestamp nghiệp vụ vào renderer; dùng `Clock.fixed(...)` trong test:

```java
Clock clock = Clock.fixed(
        Instant.parse("2026-11-12T00:00:00Z"),
        ZoneOffset.UTC
);
```

Giữ logic tính ngày/giờ trong lớp chuẩn bị model, còn template chỉ hiển thị giá trị đã được format.

## 15. Locale, fallback và message bundle

Một ứng dụng có thể dùng `MessageSource` để render subject và các câu trong email theo locale.

Ví dụ:

```properties
# mail/subjects_vi.properties
mail.subject.order-confirmed=Xác nhận đơn hàng {0}
```

```properties
# mail/subjects_en.properties
mail.subject.order-confirmed=Order {0} confirmed
```

Cấu hình test:

```java
import org.springframework.context.support
        .ResourceBundleMessageSource;

ResourceBundleMessageSource messages =
        new ResourceBundleMessageSource();

messages.setBasename("mail/subjects");
messages.setDefaultEncoding("UTF-8");
messages.setFallbackToSystemLocale(false);

String subject = messages.getMessage(
        "mail.subject.order-confirmed",
        new Object[] {"ORD-2026-001"},
        Locale.forLanguageTag("vi-VN")
);
```

Case kiểm thử:

| Trường hợp | Kỳ vọng |
|---|---|
| Locale được hỗ trợ và đủ key | Dùng đúng bản dịch và placeholder. |
| Locale vùng không có, locale ngôn ngữ có | Fallback theo quy tắc đã cấu hình. |
| Locale không hỗ trợ | Dùng default locale được duyệt hoặc báo lỗi. |
| Message key thiếu | Không tự gửi nguyên key ra subject. |
| Placeholder thiếu/thừa | Báo lỗi contract hoặc không cho phép thiếu dữ liệu quan trọng. |
| Dấu nháy đơn trong `MessageFormat` | Kiểm tra escaping/quoting đúng cú pháp. |
| Subject có emoji/CJK | Giữ Unicode sau render và MIME header encoding. |

### Đừng giả định fallback đã đúng

`ResourceBundleMessageSource` có quy tắc tìm bundle, nhưng fallback về một locale sản phẩm cụ thể cần được cấu hình/triển khai đúng. Test phải mô phỏng trường hợp thiếu locale và thiếu key để xác nhận hành vi thực tế, thay vì chỉ kiểm tra locale mặc định của máy developer.

Với email pháp lý hoặc nội dung nhạy cảm theo thị trường, có thể **không cho phép fallback** sang bản dịch khác. Khi đó thiếu key phải làm fail render để tránh gửi email sai ngôn ngữ.

### Dấu nháy trong MessageFormat

`java.text.MessageFormat` có cách diễn giải dấu nháy đơn đặc biệt. Ví dụ nội dung tiếng Anh có `don't` hoặc tiếng Pháp có dấu apostrophe có thể bị xử lý khác nếu mẫu cần format tham số.

Test nên bao gồm:

- Dấu apostrophe trong câu.
- Placeholder `{0}` và nhiều tham số.
- Dấu ngoặc nhọn cần hiển thị nguyên văn.
- Nội dung khác nhau giữa locale.

Không chỉ kiểm tra “không exception”; hãy assert subject cuối có dấu và tham số đúng.

## 16. Subject là email header, không phải HTML body

Template subject có ranh giới riêng. HTML escaping không giải quyết vấn đề newline hoặc header injection.

Ví dụ input xấu:

```text
ORD-001\r\nBcc: attacker@example.net
```

Nếu mã đơn hàng được nối trực tiếp vào subject mà không kiểm tra, ký tự điều khiển có thể tạo header không hợp lệ hoặc nguy cơ injection tùy cách build message.

Validator nên từ chối CR, LF và control character ở dữ liệu dùng trong header. Unit test:

```java
@Test
void rejectsHeaderControlCharacters() {
    String input =
            "ORD-001\r\nBcc: attacker@example.net";

    assertThatThrownBy(() ->
            MailModelValidator.requiredSingleLine(
                    input, "orderNumber"
            )
    ).isInstanceOf(IllegalArgumentException.class);
}
```

Nếu có giới hạn độ dài subject, test cả:

- `maximum - 1` code point.
- `maximum` code point.
- `maximum + 1` code point.
- Chuỗi nhiều emoji/surrogate pair.
- Chuỗi có dấu kết hợp.

**Không tự chuyển subject thành raw MIME header.** Sử dụng `MimeMessageHelper.setSubject(...)` hoặc Jakarta Mail `MimeMessage.setSubject(..., "UTF-8")` để thư viện xử lý encoding/folding. Vẫn phải validate giá trị input theo chính sách ứng dụng.

## 17. Kiểm tra output khi số lượng giá trị bằng 0

Một lỗi khá tinh vi là template ẩn giá trị số 0 vì điều kiện viết như thể 0 tương đương “không có dữ liệu”. Ví dụ:

- Số lượng item = 0.
- Tổng tiền = 0.
- Giảm giá = 0%.
- Số ngày còn lại = 0.
- Số dư hoặc phí = 0.

Cần phân biệt:

```text
value == null  -> thiếu dữ liệu
value == 0     -> có dữ liệu và giá trị bằng không
```

Ví dụ với discount:

```html
<p th:if="${discount != null}">
  Giảm giá:
  <span th:text="${discount}">0</span>
</p>
```

Test nên xác nhận phần tử có hiển thị khi `discount=0` nếu hợp đồng yêu cầu, và chỉ ẩn khi `null`.

### Dữ liệu boolean

Tương tự:

```text
isGift = false   -> giá trị hợp lệ
isGift = null    -> thiếu trạng thái
```

Nếu template có điều kiện theo boolean, test cả true, false và null theo chính sách. Không coi null và false là một nếu cần phân biệt “chưa xác định” với “không”.

## 18. Đảm bảo tính nhất quán giữa subject, HTML và plain text

Email giao dịch thường có nhiều bản thể hiện của cùng nội dung:

- Subject: “Xác nhận đơn hàng ORD-001”.
- Plain text: nội dung cho mail client không hỗ trợ HTML.
- HTML: phiên bản có layout, link và hình ảnh.

Nếu ba bản dùng dữ liệu khác nhau hoặc format ở các thời điểm khác nhau, người nhận có thể thấy subject ghi mã đơn hàng A nhưng body ghi mã B.

Một model kết quả:

```java
public record RenderedMail(
        String subject,
        String plainText,
        String html
) {
}
```

Một service renderer nên nhận **cùng một snapshot model và locale** rồi trả về `RenderedMail`.

### Kiểm thử semantic consistency

Ví dụ:

```java
@Test
void keepsOrderNumberConsistentAcrossAllParts() {
    RenderedMail result = renderer.render(
            OrderMailFixtures.validOrder(),
            Locale.forLanguageTag("vi-VN"),
            ZoneId.of("Asia/Ho_Chi_Minh")
    );

    String expected = "ORD-2026-001";

    assertThat(result.subject()).contains(expected);
    assertThat(result.plainText()).contains(expected);

    assertThat(
            Jsoup.parse(result.html())
                    .selectFirst("[data-test=order-number]")
                    .text()
    ).isEqualTo(expected);
}
```

`renderer` minh họa một component ứng dụng trả về cả ba phần. Một test tương tự nên xác nhận total, deadline hoặc các giá trị quan trọng giống nhau về ngữ nghĩa, kể cả khi cách trình bày của HTML/plain text khác nhau.

### Plain text không nên chỉ là HTML bị xóa tag một cách ngây thơ

Đơn giản strip tag có thể làm mất URL, cấu trúc bảng, xuống dòng và dấu phân cách. Có thể dùng template plain text riêng hoặc một converter được test kỹ.

Các edge case của plain text:

- Nhiều dòng, dòng trống và newline.
- Link dài.
- Danh sách sản phẩm.
- Unicode và emoji.
- Dấu `<`, `>` và `&` phải giữ đúng dạng văn bản.
- Không còn placeholder chưa render như `${name}`.
- Không in lại HTML entity như `&amp;` khi người nhận đọc plain text.

## 19. Kiểm thử MIME sau khi render nhưng trước khi gửi SMTP

Sau khi đã có `RenderedMail`, có thể dựng MIME message ngay trong test và kiểm tra các part mà không kết nối mạng.

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.util.ArrayList;
import java.util.List;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

@Test
void createsPlainTextAndHtmlMimeParts() throws Exception {
    RenderedMail content = renderer.render(
            OrderMailFixtures.validOrder(),
            Locale.forLanguageTag("vi-VN"),
            ZoneId.of("Asia/Ho_Chi_Minh")
    );

    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    MimeMessage message = sender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

    helper.setFrom("orders@example.org");
    helper.setTo("customer@example.net");
    helper.setSubject(content.subject());
    helper.setText(content.plainText(), content.html());

    message.saveChanges();

    assertThat(message.getSubject())
            .isEqualTo(content.subject());

    List<String> contentTypes = new ArrayList<>();
    collectLeafTypes(message, contentTypes);

    assertThat(contentTypes)
            .anyMatch(type -> type.startsWith("text/plain"));
    assertThat(contentTypes)
            .anyMatch(type -> type.startsWith("text/html"));
}

static void collectLeafTypes(
        Part part,
        List<String> types
) throws Exception {
    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();

        for (int index = 0;
                index < multipart.getCount();
                index++) {
            collectLeafTypes(
                    multipart.getBodyPart(index),
                    types
            );
        }
    } else {
        types.add(part.getContentType().toLowerCase(
                java.util.Locale.ROOT
        ));
    }
}
```

Đoạn code kiểm tra có cả `text/plain` và `text/html` dù MIME có thể lồng nhiều tầng `multipart`. Đừng viết test mặc định “part thứ hai luôn là HTML” vì `MimeMessageHelper` có các multipart mode và cấu trúc có thể khác tùy attachment/inline resource.

`message.saveChanges()` thực hiện bước chuẩn bị MIME trong bộ nhớ; **không gọi `mailSender.send(message)`** nên test không cần SMTP host hoặc credential.

## 20. Nội dung có attachment và ảnh inline

Template có thể tham chiếu ảnh qua CID:

```html
<img src="cid:brand-logo" alt="Logo">
```

Khi render với dữ liệu biên, cần kiểm tra:

- CID trong HTML khớp với Content-ID được builder thêm.
- Ảnh inline không bị thiếu khi dữ liệu optional.
- `alt` có ý nghĩa khi ảnh không tải được.
- Nguồn ảnh không được lấy từ đường dẫn/URL tùy ý.
- Attachment filename có ký tự đặc biệt được xử lý theo policy.
- File không quá lớn; stream còn tồn tại khi MIME serialize.

Những yêu cầu này chủ yếu thuộc **MIME builder test** hoặc security test của attachment, không phải test HTML escaping thuần túy. Tách tầng giúp test dễ đọc và biết lỗi ở đâu.

### Không render đường dẫn resource trực tiếp từ người dùng

Nếu template cho phép chọn logo hoặc fragment theo tên, dùng mapping ID sang resource đã được cho phép. Input như `../../secrets` không được trở thành template path hoặc file path.

Test các resource key không hợp lệ trước khi tiến tới MIME construction.

## 21. Kiểm thử template thiếu key, fragment hoặc variable

Những lỗi thường chỉ lộ khi deploy:

- File template bị đặt sai folder hoặc sai suffix.
- Fragment được đổi tên nhưng template chính vẫn tham chiếu tên cũ.
- Message bundle thiếu key của một locale.
- Đổi tên field trong view model nhưng template chưa cập nhật.
- Một field null dẫn tới exception ở biểu thức property dereference.
- Template cache đang chứa bản cũ.

### Kiểm tra resource có tồn tại

Khi dùng `ClassLoaderTemplateResolver`, test xử lý một template có tên cố định:

```java
@Test
void rendersExpectedTemplateResource() {
    Context context = new Context(Locale.ENGLISH);
    context.setVariable("customerName", "Ada");
    context.setVariable("orderNumber", "ORD-001");
    context.setVariable("lines", List.of());
    context.setVariable("formattedTotal", "0");
    context.setVariable("detailUrl",
            "https://shop.example.org/orders/ORD-001");

    String html = engine.process(
            "order-confirmed", context
    );

    assertThat(html).contains("ORD-001");
}
```

Nếu yêu cầu engine chỉ được dùng những template đã được xác định, hãy hạn chế việc chọn template name từ external input. Không dùng client-supplied string làm đường dẫn template trong email rendering.

### Kiểm tra biến bắt buộc không bị rơi khỏi model

Không nên chỉ dựa vào Thymeleaf tự hiển thị rỗng khi thiếu variable. Có thể:

1. Validate model ở ranh giới input.
2. Có schema/contract cho các field mà template yêu cầu.
3. Test mọi notification type với fixture hợp lệ tối thiểu.
4. Khi thay đổi template, cập nhật mapping/fixture trong cùng thay đổi.

Nếu một biến bắt buộc không có, lỗi nên biểu hiện trước khi tạo message thay vì gửi email có những khoảng trống khó nhận thấy.

## 22. Test exception và nguyên tắc không gửi email lỗi

Một quy tắc quan trọng: nếu dữ liệu không hợp lệ hoặc renderer thất bại, **không được gọi SMTP**.

Ví dụ service orchestration:

```java
public void sendOrderConfirmation(OrderMailModel model) {
    RenderedMail rendered = renderer.render(
            model, localePolicy.forOrder(model),
            zonePolicy.forOrder(model)
    );

    MimeMessage message = messageBuilder.build(
            model, rendered
    );

    mailSender.send(message);
}
```

Test với mock:

```java
@Test
void doesNotSendWhenRequiredDataIsMissing() {
    OrderMailModel invalid = withOrderNumber(
            OrderMailFixtures.validOrder(),
            null
    );

    assertThatThrownBy(() ->
            notificationService.sendOrderConfirmation(invalid)
    ).isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(mailSender);
}
```

Các helper/model/service là thành phần minh họa và phải được khởi tạo trong test fixture. Điều quan trọng là **test cả lỗi được trả về lẫn tác động không xảy ra**.

### Phân biệt lỗi render với lỗi SMTP

- Lỗi render: thiếu dữ liệu, sai template, không tìm thấy key, invalid URI.
- Lỗi MIME builder: header không hợp lệ, attachment resource không đọc được.
- Lỗi SMTP: authentication, network, server rejection.

Nếu catch tất cả exception rồi trả “gửi thất bại” chung, hệ thống khó sửa đúng nguyên nhân. Trong log và delivery record, nên ghi loại lỗi riêng nhưng tránh để lộ nội dung nhạy cảm.

## 23. Dữ liệu biên cho subject và template đa ngôn ngữ

Các case liên quan ngôn ngữ và encoding:

| Trường hợp | Điều cần xác minh |
|---|---|
| Tên tiếng Việt có dấu | Giữ đúng ký tự Unicode trong HTML/plain/subject. |
| Emoji trong tên người dùng | Không mất surrogate pair. |
| CJK | Không xuất hiện ký tự thay thế `�`. |
| Arabic/RTL | Nội dung không đảo thứ tự dữ liệu quan trọng; visual test riêng. |
| Dấu nháy đơn trong subject bundle | `MessageFormat` xử lý đúng. |
| Locale không hỗ trợ | Fallback hoặc fail theo policy. |
| Locale có dấu phân cách số khác | Không format từ JVM default. |
| Currency khác locale | Dùng currency của giao dịch. |
| Timestamp sát nửa đêm | Dùng đúng time zone của recipient. |
| Template text có ký tự `<` và `&` | Escape HTML đúng, plain text không bị encode sai. |

Các test có thể chạy ở CI với default locale/time zone được cố ý thay đổi trong một nhóm riêng để phát hiện phụ thuộc ngầm. Tuy nhiên, tránh thay các biến global JVM đồng thời giữa các test song song nếu không có isolation.

## 24. Snapshot test: hữu ích nhưng cần dùng đúng

Một số dự án lưu bản HTML render mẫu làm **snapshot/golden file**. Khi template thay đổi, test so sánh output mới với output được duyệt.

Lợi ích:

- Phát hiện nội dung/layout fragment bị thay đổi ngoài ý muốn.
- Review diff của subject/HTML/plain text.
- Hỗ trợ quy trình duyệt nội dung.
- Đặc biệt hữu ích khi nhiều locale cùng tồn tại.

Hạn chế:

- Thay đổi whitespace hoặc thứ tự attribute có thể gây diff không quan trọng.
- Snapshot lớn khó đọc; người review có thể approve máy móc.
- Snapshot không tự xác nhận HTML an toàn hoặc dữ liệu nghiệp vụ đúng.
- Nếu timestamp, UUID hoặc thứ tự map không cố định, snapshot dễ flake.
- Nếu chứa PII thật, snapshot là một đường rò rỉ vào repository.

### Chiến lược cân bằng

Nên kết hợp:

1. **Semantic assertions:** DOM chứa đúng nội dung, link, số lượng phần tử.
2. **Security assertions:** markup injection không biến thành DOM.
3. **Contract assertions:** biến bắt buộc/optional, fallback, locale.
4. **Snapshot chọn lọc:** một số trường hợp quan trọng đã ổn định.

Không thay toàn bộ test bằng snapshot hoặc chỉ dùng `assertThat(html).isNotBlank()`. Một template render ra chuỗi dài nhưng sai mã đơn hàng vẫn có thể vượt qua những assert yếu.

## 25. Property-based testing cho input khó đoán

Ngoài các giá trị biên đã chọn, có thể dùng **property-based testing** để sinh nhiều chuỗi Unicode, độ dài và tổ hợp ký tự đặc biệt.

Một số invariant có thể kiểm:

- Renderer không tạo phần tử `script` từ `customerName`.
- Render không chứa newline bất hợp lệ trong subject.
- Chuỗi được xuất dưới `th:text` khi parse DOM có text tương ứng input.
- Renderer không phụ thuộc vào thứ tự không xác định nếu input có thứ tự rõ.
- Với dữ liệu hợp lệ, output chứa đúng notification ID/order number.
- Với dữ liệu không hợp lệ, không có đường đi tới `JavaMailSender.send`.

Các thư viện như jqwik hoặc QuickTheories có thể hỗ trợ sinh dữ liệu. Đây là tầng bổ sung, không thay thế các case nghiệp vụ cụ thể hoặc review thủ công.

### Tại sao cần seed ổn định?

Khi fuzz/property test phát hiện lỗi, cần lưu seed và mẫu tối thiểu để tái hiện. Nếu không, lỗi có thể xuất hiện một lần trên CI rồi biến mất khi chạy lại, khó chẩn đoán.

## 26. Hiệu năng và tài nguyên ở dữ liệu cực trị

Template có danh sách dài hoặc note lớn có thể làm tăng thời gian render và bộ nhớ. Những test liên quan gồm:

- 1, 10, 100, 1.000 item (tùy giới hạn nghiệp vụ).
- Note vài KB hoặc gần ngưỡng cho phép.
- Nhiều fragment lặp hoặc template nested.
- Nhiều locale cùng render.
- Một số lượng lớn thông báo được render đồng thời.

**Unit test thời gian chạy cứng** như “phải render dưới 20 ms” thường không ổn định trên CI. Thay vì đó:

- Xác nhận input vượt giới hạn được từ chối sớm.
- Dùng benchmark/performance test riêng trong môi trường phù hợp.
- Đo p95/p99 render latency ở môi trường vận hành.
- Kiểm tra template cache và tránh N+1 database queries trong renderer.
- Không cho template tự truy cập repository hoặc dịch vụ từ xa.

Unit test boundary nên bảo vệ **ngưỡng dữ liệu và contract**, còn benchmark đo đặc tính hiệu năng dưới tải được kiểm soát.

## 27. Ma trận dữ liệu biên tối thiểu

Để thiết kế bộ test có hệ thống, có thể dùng ma trận sau:

| Nhóm | Case | Kỳ vọng kiểm thử |
|---|---|---|
| Required text | `null`, `""`, whitespace | Fail-fast hoặc fallback theo contract. |
| Optional text | `null`, rỗng, whitespace | Không tạo nhãn/khối HTML trống. |
| HTML injection | `<script>`, `<img onerror>`, `&<>` | Text được escape, không tạo element độc hại. |
| Subject injection | CR/LF, control character | Reject trước MIME builder. |
| Unicode | Tiếng Việt, CJK, emoji, RTL | Giữ ký tự, không lỗi encoding. |
| Long text | Sát giới hạn và vượt giới hạn | Chấp nhận/từ chối theo policy, không cắt sai. |
| List | `null`, 0, 1, nhiều, phần tử null | Đúng số dòng, thứ tự và error semantics. |
| Money | 0, âm, rất lớn, precision cao | Format/rounding đúng nghiệp vụ. |
| Time | Nửa đêm, DST, leap day | Đúng locale và time zone. |
| URL | HTTPS hợp lệ, `javascript:`, host giả | Dùng link hợp lệ hoặc reject. |
| Locale | Hợp lệ, thiếu bundle, thiếu key | Fallback/fail theo quy tắc. |
| Template resource | File thiếu, fragment sai | Lỗi có thể quan sát, không gửi SMTP. |
| Cross-format | Subject, plain, HTML | Các giá trị quan trọng đồng nhất. |
| MIME | UTF-8, alternative, inline/attachment | Header và các part đúng, không cần SMTP. |
| Reproducibility | Clock cố định, fixture ổn định | Test chạy lại cho cùng kết quả. |

Đây là ma trận khởi đầu. Mỗi notification type có thể cần thêm các case đặc thù: số ghế = 0, mã vận đơn chưa có, coupon hết hạn, người nhận không có tên, đơn hàng được hoàn tiền, nội dung theo vùng pháp lý v.v.

## 28. Quy trình đề xuất khi thêm một email template mới

Một quy trình đơn giản có thể áp dụng:

1. **Định nghĩa model:** liệt kê trường bắt buộc, optional, kiểu dữ liệu, giới hạn và nguồn.
2. **Chốt policy:** fallback, locale, time zone, money rounding, URL host, xử lý whitespace.
3. **Xây fixture hợp lệ tối thiểu:** không dùng dữ liệu production.
4. **Tạo template:** dùng escaped text output, tách subject/HTML/plain.
5. **Viết test required/optional:** giá trị `null`, rỗng và biên.
6. **Viết test nội dung nguy hiểm:** HTML injection, URL scheme, control character.
7. **Viết test semantic:** mã đơn, tiền, ngày và danh sách.
8. **Viết test đa ngôn ngữ:** Unicode, placeholder, fallback.
9. **Viết test MIME:** subject UTF-8, text/plain + text/html, attachment/CID nếu có.
10. **Viết test lỗi:** renderer lỗi phải chặn việc gửi SMTP.
11. **Review snapshot/preview:** xác nhận nội dung và bố cục trên email client mục tiêu.
12. **Khi template đổi:** cập nhật hợp đồng và các test có chủ đích, không chỉ cập nhật snapshot.

Nếu hệ thống có nhiều loại email, có thể tạo **test contract dùng chung** cho các yêu cầu phổ biến (không rò rỉ HTML, không null required, không dữ liệu vượt giới hạn), đồng thời giữ test riêng cho ý nghĩa nghiệp vụ từng template.

## 29. Những lỗi thường gặp khi kiểm thử template

| Triệu chứng | Nguyên nhân phổ biến | Cách cải thiện |
|---|---|---|
| Test pass nhưng email chứa chữ `null` | Chỉ assert output không rỗng | Validate required field và assert nội dung DOM. |
| Chuỗi `<script>` được đưa thành element | Dùng unescaped output | Dùng `th:text` và security assertions. |
| Link trong email trỏ sai site | Tin URL từ input | Xây link từ origin tin cậy, allowlist host và test URL. |
| Test không phát hiện thiếu bản dịch | Chỉ chạy default locale | Test các locale được hỗ trợ và missing key. |
| Test phụ thuộc máy CI | Dùng system clock/time zone/locale | Truyền Clock, ZoneId và Locale tường minh. |
| Số tiền hiển thị không nhất quán | Dùng floating point hoặc format trong nhiều lớp | Dùng BigDecimal và formatter có contract rõ. |
| Empty list gây layout rỗng | Không test zero item | Test 0/1/n item và conditional block. |
| Header lỗi khi tên chứa newline | Không có validation cho subject | Reject control characters trước MIME. |
| Test MIME chỉ kiểm tra một part index | Multipart mode tạo nested structure | Duyệt cây MIME theo content type. |
| Unit test gửi email thật | Renderer gắn với transport | Tách renderer khỏi JavaMailSender, SMTP test riêng. |
| Snapshot thay đổi liên tục | UUID/time/random order không ổn định | Dùng fixture/clock cố định, semantic assertions. |
| Test dữ liệu dài làm CI quá chậm | Không có giới hạn input hợp lệ | Kiểm tra size limit và benchmark riêng. |
| Optional note có nhãn nhưng không có giá trị | Chỉ ẩn text node, không ẩn cả block | Điều kiện trên cả khối và test DOM. |
| Người nhận thấy email HTML nhưng plain text sai | Chỉ test HTML | Render/test cả plain, subject và semantic consistency. |

## 30. Ghi nhớ

- **Boundary-value testing** cố tình thử `null`, rỗng, whitespace, 0, danh sách cực trị, chuỗi dài, Unicode và input độc hại; không chỉ dùng dữ liệu mẫu “đẹp”.
- Phân biệt dữ liệu **required** và **optional**; lỗi required nên dừng trước khi gọi SMTP.
- Test renderer **độc lập với `JavaMailSender.send(...)`** để biết lỗi xuất phát từ nội dung hay transport.
- Với Thymeleaf, dùng `th:text` cho dữ liệu không đáng tin và xác minh qua DOM; tránh `th:utext` trừ khi có nội dung đã được kiểm soát.
- URL trong HTML phải được xây/validate theo chính sách; HTML escaping một mình không bảo vệ khỏi `javascript:` hoặc host giả.
- Subject là header: chặn CR/LF, control characters và kiểm tra độ dài riêng.
- Tạo fixture ổn định, dùng `Clock`/`ZoneId`/`Locale` rõ ràng, không phụ thuộc môi trường CI.
- Dùng `BigDecimal`, currency policy và formatter thống nhất cho dữ liệu tài chính.
- Test `null`, 0, 1 và nhiều phần tử cho collection; đừng để output bỏ sót giá trị 0 hợp lệ.
- Kiểm thử đồng nhất subject, plain text và HTML; không dùng test “HTML không rỗng” làm tiêu chí duy nhất.
- Có thể dùng `MimeMessageHelper` để kiểm tra cấu trúc MIME trong bộ nhớ, **không cần kết nối SMTP**.
- Kết hợp semantic assertions, security assertions và snapshot chọn lọc; với layout, cần visual test riêng trên email client.
- Khi renderer lỗi, ghi nhận nguyên nhân và **không gửi email lỗi** cho người nhận.

**Kết luận:** Một template email có chất lượng không chỉ render đẹp với dữ liệu chuẩn mà còn xử lý đúng những dữ liệu khó nhất ở ranh giới hợp đồng. Unit test với dữ liệu biên giúp phát hiện lỗi nội dung, an toàn HTML/header, định dạng đa ngôn ngữ và tính nhất quán trước khi message được giao cho Spring Mail. Thiết kế hợp đồng input rõ, test có thể tái hiện và tách renderer khỏi SMTP là nền tảng để hệ thống email phát triển mà không tạo ra thông báo sai hoặc rò rỉ dữ liệu.
