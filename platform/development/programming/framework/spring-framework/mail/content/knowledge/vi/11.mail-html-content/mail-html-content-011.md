# Kiểm tra HTML sau khi render bằng dữ liệu biên

Trong **Spring Framework Mail**, email HTML thường được tạo từ một template và dữ liệu nghiệp vụ: tên người dùng, số lượng sản phẩm, số tiền, đường dẫn xác minh, danh sách hàng hóa hoặc thông báo. Một template trông đúng với dữ liệu mẫu chưa chắc đúng sau khi render bằng dữ liệu thực. Tên dài có thể phá bố cục, tiếng Việt lỗi encoding, chuỗi trông giống HTML có thể bị diễn giải thành markup, một URL chứa `&` có thể bị hỏng, hoặc danh sách rỗng để lại một bảng vô nghĩa.

**Kiểm tra HTML sau khi render bằng dữ liệu biên** nghĩa là chủ động đưa những giá trị nằm ở ranh giới hợp lệ, giá trị thiếu và đầu vào có nguy cơ gây lỗi vào quá trình render; sau đó đánh giá **HTML kết quả**, không chỉ xem file template. Bài học hướng dẫn cách tổ chức pipeline render, thiết kế bộ dữ liệu biên, kiểm tra escaping, nội dung, URL, hình ảnh, MIME, bố cục trong email client và tạo kiểm thử tự động bằng Spring Boot.

## 1. Vì sao phải kiểm tra sau khi render?

Template có thể chứa biểu thức Thymeleaf:

```html
<p>Xin chào, <span th:text="${displayName}">bạn</span>!</p>
<p>Bạn có <strong th:text="${itemCount}">0</strong> sản phẩm.</p>
```

Sau khi render với `displayName="Nguyễn An"` và `itemCount=2`, đầu ra có thể là:

```html
<p>Xin chào, <span>Nguyễn An</span>!</p>
<p>Bạn có <strong>2</strong> sản phẩm.</p>
```

Nhưng nếu `displayName` chứa `<img src=x onerror=alert(1)>` và ứng dụng ghép trực tiếp bằng nối chuỗi, dữ liệu có thể trở thành thẻ HTML thay vì văn bản. Dùng `th:text` giúp escape nội dung ở ngữ cảnh HTML text. Nếu `itemCount` là số âm hoặc không có dữ liệu, engine vẫn có thể tạo HTML hợp cú pháp nhưng **sai nghĩa nghiệp vụ**.

Ba lớp kiểm tra cần phân biệt:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| **Dữ liệu/model** | Giá trị có hợp lệ, được chuẩn hóa và định dạng đúng không? | Số sản phẩm không âm, token xác minh không rỗng. |
| **HTML đã render** | Nội dung/markup/link đã đúng chưa? | Dữ liệu chứa `<script>` không tạo phần tử script. |
| **MIME và email client** | Thư được đóng gói, truyền và hiển thị đúng không? | HTML và text/plain cùng thông tin, CID ảnh hợp lệ, nút không tràn khung. |

Một SMTP server trả `250` sau `DATA` thường chỉ xác nhận đã **tiếp nhận thông điệp**. Nó không chứng minh HTML hiển thị đúng, thư đã đến Inbox hoặc người nhận đã đọc.

## 2. Xây dựng ma trận dữ liệu biên

Không nên chỉ kiểm tra một bộ dữ liệu “Nguyễn Văn A, 2 sản phẩm, 100.000 đồng”. Một bộ dữ liệu có hệ thống có thể gồm:

| Nhóm | Trường hợp thử | Kỳ vọng hoặc điều cần xem |
|---|---|---|
| Thiếu giá trị | `null` | Fallback rõ ràng hoặc lỗi có chủ đích; không in chuỗi `null`. |
| Rỗng và khoảng trắng | `""`, `"   "`, tab, xuống dòng | Không tạo lời chào trống hoặc khoảng cách bất thường. |
| Tên rất dài | 200–500 ký tự, không có dấu cách | Không tràn bố cục; giới hạn hiển thị nếu nghiệp vụ cho phép. |
| HTML đặc biệt | `A&B <C> "D"` | Được escape, giữ nghĩa văn bản. |
| Chuỗi giống mã độc | `<script>alert(1)</script>`, `<img onerror=...>` | Không thành thẻ/attribute do người dùng chèn. |
| Tiếng Việt | `Nguyễn Thị Ánh`, `Đắk Lắk` | Không lỗi dấu hoặc encoding. |
| Unicode khác | `日本語`, `العربية`, `😊` | Không mất ký tự, không cắt giữa surrogate pairs. |
| URL | Dấu `&`, `#`, query nhiều tham số | Encode đúng trong cả URL và HTML attribute. |
| URL không tin cậy | `javascript:...`, `https://attacker.invalid` | Bị từ chối hoặc chỉ dùng base URL được phép. |
| Số | `0`, số âm, số rất lớn, thập phân | Kiểm tra ràng buộc và định dạng. |
| Ngày giờ | Cuối tháng, ngày 29/2, ranh giới múi giờ | Hiển thị đúng timezone và locale. |
| Danh sách | `null`, rỗng, một phần tử, hàng trăm phần tử | Có nhánh empty và giới hạn nội dung. |
| Ảnh | Logo mất, CID không khớp | Không có ảnh lỗi khó hiểu hoặc lỗi chuẩn bị không được nhận diện. |
| Nội dung lớn | HTML dài, nhiều ảnh/tệp | Xem giới hạn kích thước mail và cách client rút gọn. |

**Không phải mọi edge case đều phải được chấp nhận.** Có trường hợp cần fallback (tên hiển thị rỗng); có trường hợp phải từ chối (token xác minh thiếu hoặc giá trị tiền không hợp lệ). Điều quan trọng là hệ thống có hành vi dự kiến và kiểm tra được.

## 3. Pipeline render trước khi gửi SMTP

```text
Sự kiện nghiệp vụ
      |
      v
Validate dữ liệu bắt buộc
      |
      v
Normalize/format (fallback, locale, timezone, giới hạn)
      |
      v
Template engine -> HTML đã render + plain text
      |
      v
Kiểm tra kết quả trên các dữ liệu biên
      |
      v
MimeMessageHelper.setText(plain, html)
      |
      v
addInline(...) / addAttachment(...) nếu cần
      |
      v
JavaMailSender.send(...) -> SMTP relay
```

Nên **tách renderer và sender**. Renderer trả về HTML/text mà không kết nối mạng; sender tạo MIME và gửi. Nhờ đó, hàng chục trường hợp dữ liệu biên có thể được thực thi ở mức unit/integration test mà không gửi email thật.

## 4. Ví dụ đầy đủ với Spring Boot và Thymeleaf

Ví dụ dựa trên Spring Boot 3.x, Spring Framework 6.x và Java 17+. Thymeleaf được dùng để tạo HTML string cho email; không cần request HTTP.

### 4.1. Dependency

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

### 4.2. Template HTML

Tệp `src/main/resources/templates/mail/account-confirmation.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Xác minh tài khoản</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;">
  <table role="presentation" cellpadding="0" cellspacing="0"
         style="width:100%;background:#f5f5f5;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" cellpadding="0" cellspacing="0"
               style="width:100%;max-width:600px;background:#fff;">
          <tr>
            <td style="padding:24px;font-family:Arial,sans-serif;">
              <h1 style="font-size:24px;line-height:1.3;">
                Xin chào, <span th:text="${displayName}">bạn</span>!
              </h1>

              <p style="line-height:1.6;">
                Vui lòng xác minh tài khoản để hoàn tất đăng ký.
              </p>

              <p>
                <a th:href="${verificationUrl}"
                   style="display:inline-block;padding:12px 20px;
                          background:#174ea6;color:#fff;
                          text-decoration:none;">
                  Xác minh tài khoản
                </a>
              </p>

              <p th:if="${hasNotifications}">
                Bạn có
                <strong th:text="${notificationCount}">0</strong>
                thông báo đang chờ.
              </p>

              <p th:unless="${hasNotifications}">
                Hiện chưa có thông báo nào cần xem.
              </p>

              <p style="font-size:13px;line-height:1.5;">
                Nếu không yêu cầu tạo tài khoản,
                bạn có thể bỏ qua email này.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

Ở đây:
- `th:text` chèn dữ liệu vào vùng text và escape HTML theo ngữ cảnh.
- `th:href` đặt thuộc tính liên kết; **URL vẫn phải được validate hoặc tạo từ base URL tin cậy**.
- `th:if` và `th:unless` chọn nội dung dựa trên số thông báo.
- `lang="vi"`, UTF-8 và bố cục table/inline styles giúp định hướng hiển thị email, dù cần kiểm thử trên các client mục tiêu.

### 4.3. Kết quả renderer

```java
package com.example.mail;

public record RenderedEmail(
    String plainText,
    String htmlText
) {}
```

Mô hình trả đồng thời hai phiên bản nội dung để kiểm tra được ngay sau render. Không gắn SMTP vào API của renderer.

### 4.4. Renderer: validate, normalize, render

```java
package com.example.mail;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.springframework.stereotype.Component;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Component
public class AccountEmailRenderer {
    private static final int MAX_NAME_CODEPOINTS = 80;

    private final SpringTemplateEngine templateEngine;

    public AccountEmailRenderer(SpringTemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    public RenderedEmail render(
            String rawName,
            String verificationToken,
            int notificationCount) {

        if (verificationToken == null || verificationToken.isBlank()) {
            throw new IllegalArgumentException(
                "Thiếu verification token"
            );
        }
        if (notificationCount < 0) {
            throw new IllegalArgumentException(
                "notificationCount không được âm"
            );
        }

        String name = normalizeName(rawName);
        String url = "https://accounts.example.com/verify?token="
            + URLEncoder.encode(
                verificationToken, StandardCharsets.UTF_8
            );

        Context context = new Context(Locale.forLanguageTag("vi"));
        context.setVariable("displayName", name);
        context.setVariable("verificationUrl", url);
        context.setVariable("notificationCount", notificationCount);
        context.setVariable(
            "hasNotifications", notificationCount > 0
        );

        String html = templateEngine.process(
            "mail/account-confirmation", context
        );

        String plain = "Xin chào, " + name + "!\n"
            + "Vui lòng xác minh tài khoản tại:\n"
            + url + "\n"
            + (notificationCount > 0
                ? "Bạn có " + notificationCount
                    + " thông báo đang chờ.\n"
                : "Hiện chưa có thông báo nào cần xem.\n")
            + "Nếu không yêu cầu đăng ký, bạn có thể bỏ qua thư.";

        return new RenderedEmail(plain, html);
    }

    private static String normalizeName(String raw) {
        if (raw == null || raw.isBlank()) {
            return "bạn";
        }
        String name = raw.strip();
        int count = name.codePointCount(0, name.length());
        if (count <= MAX_NAME_CODEPOINTS) {
            return name;
        }
        int end = name.offsetByCodePoints(0, MAX_NAME_CODEPOINTS);
        return name.substring(0, end) + "…";
    }
}
```

Một số điểm thiết kế:

1. **Token rỗng** không sinh đường dẫn `#` giả; renderer từ chối dữ liệu bắt buộc bị thiếu.
2. Số thông báo âm được xem là lỗi dữ liệu thay vì hiển thị số âm.
3. Tên rỗng trở thành `"bạn"`. Giới hạn theo Unicode code point tránh cắt đôi một surrogate pair; nếu cần cắt đúng **grapheme cluster** của các emoji phức tạp, dùng cơ chế segmentation phù hợp.
4. URL được tạo từ base HTTPS cố định và token được mã hóa trong query. Không nhận toàn bộ đích URL tùy ý từ người dùng.
5. Thymeleaf escape biến `name` khi đưa vào `th:text`; renderer không tự tin tưởng dữ liệu đầu vào là markup.
6. URL chứa token là dữ liệu nhạy cảm. Không ghi URL hay toàn bộ HTML đã render vào log production.

### 4.5. Tạo MIME sau khi render

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountVerificationMailService {
    private final AccountEmailRenderer renderer;
    private final JavaMailSender sender;

    public AccountVerificationMailService(
            AccountEmailRenderer renderer,
            JavaMailSender sender) {
        this.renderer = renderer;
        this.sender = sender;
    }

    public void send(
            String recipient,
            String displayName,
            String token,
            int notificationCount) throws MessagingException {

        RenderedEmail rendered = renderer.render(
            displayName, token, notificationCount
        );

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message, true, "UTF-8"
        );
        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Xác minh tài khoản");
        helper.setText(
            rendered.plainText(), rendered.htmlText()
        );

        sender.send(message);
    }
}
```

Thứ tự rõ ràng: **validate → render → hoàn thiện MIME → send**. Với ảnh inline, gọi `addInline(...)` sau `setText(...)` và đảm bảo CID khớp HTML. Khi template lỗi, gửi SMTP chưa bắt đầu. Khi SMTP lỗi, có thể quản lý attempt trong outbox/queue riêng.

## 5. Dữ liệu biên kiểu chuỗi và Unicode

### 5.1. Null, chuỗi rỗng và chỉ có khoảng trắng

Thử lần lượt:

```text
null
""
" "
"   "
"\t"
"\n"
```

Với tên hiển thị tùy chọn, HTML kỳ vọng:

```html
<h1>Xin chào, <span>bạn</span>!</h1>
```

Cần phân biệt giá trị **tùy chọn** có thể dùng fallback và giá trị **bắt buộc** phải báo lỗi. Không thay mọi `null` thành chuỗi `"-"` một cách máy móc: email xác minh thiếu token phải dừng, trong khi tên hiển thị thiếu có thể dùng từ xưng hô chung.

### 5.2. Ký tự đặc biệt và nội dung trông giống markup

Bộ input thử:

```text
A&B
<Quý khách>
"Ưu đãi" & 'Khuyến mãi'
<script>alert(1)</script>
<img src=x onerror=alert(1)>
</td><td>Chèn nội dung
```

Đầu ra cần giữ các chuỗi này là **dữ liệu văn bản**. Chẳng hạn `<Quý khách>` trong source HTML nên xuất hiện ở dạng tương đương `&lt;Quý khách&gt;` khi đi qua `th:text`.

**Escaping khác sanitization:**
- *Escaping* biến ký tự đặc biệt thành entity phù hợp để hiển thị text.
- *Sanitization* cho phép một tập markup nhỏ sau khi loại bỏ thẻ và thuộc tính nguy hiểm, khi nghiệp vụ thực sự cần rich text.
- *URL validation* kiểm soát scheme và host của liên kết.
- *Header validation* kiểm soát dữ liệu đưa vào `Subject`, `From` và các header MIME.

Không dùng `th:utext` trực tiếp với nội dung người dùng chưa được kiểm soát. Dù mail client thường loại bỏ script, không được phụ thuộc vào hành vi của client để làm lớp bảo vệ chính.

### 5.3. Ký tự nhiều byte và hướng viết

Thử `Nguyễn Thị Ánh`, `Đắk Lắk`, `Café`, `日本語`, `العربية`, `😊` và emoji nhiều thành phần.

Ba khái niệm độ dài khác nhau:
- `String.length()` đếm UTF-16 code unit;
- `codePointCount(...)` đếm Unicode code point;
- một ký tự người dùng nhìn thấy có thể là **grapheme cluster** gồm nhiều code point.

Với nội dung có chữ Ả Rập kết hợp số và URL, thử thêm tính năng RTL trên email client mục tiêu. Hỗ trợ CSS và thuộc tính hướng viết không hoàn toàn giống nhau giữa các mail client.

### 5.4. Chuỗi rất dài

Thử tên 300 ký tự, từ không có dấu cách, mã đơn hàng dài hoặc query token dài. Kiểm tra **logic hiển thị** (cắt/giới hạn có chủ đích) và **layout thực tế** (nút CTA, bảng, ô trên màn hình nhỏ). Không tự động cắt những định danh nghiệp vụ phải hiển thị đầy đủ; có thể cần cách trình bày khác hoặc link xem chi tiết.

## 6. URL sau render: không chỉ là HTML escaping

Ví dụ:

```html
<a th:href="${verificationUrl}">Xác minh tài khoản</a>
```

Việc template escape giá trị thuộc tính **không biến mọi URL thành đáng tin cậy**. Các giá trị sau phải bị chặn hoặc được xử lý theo chính sách:

```text
javascript:alert(1)
data:text/html,...
http://accounts.example.com/verify
https://attacker.invalid/login
//attacker.invalid/path
${unresolved-placeholder}
```

Với link xác minh, nên tạo URL từ base HTTPS do ứng dụng quản lý, không cho phép người dùng chọn host. Kiểm tra HTML đã render:
- `href` không rỗng, không còn placeholder template.
- URL tuyệt đối và dùng HTTPS trong trường hợp cần bảo vệ.
- Host thuộc allowlist tin cậy.
- Query parameter được encode đúng; khi parse HTML, ký tự `&` không làm vỡ attribute.
- Token không bị cắt, không đi vào nơi ghi log.
- Link không trỏ nhầm `localhost` hoặc staging khi phát hành production.
- Nếu có unsubscribe, endpoint phải thực sự xử lý hủy đăng ký và quyền tương ứng, không chỉ là URL minh họa.

Với token chứa các ký tự đặc biệt như `+`, `/`, `=`, phải encode theo ngữ cảnh query. Đừng nối raw token tùy ý mà không xét ký tự dành riêng của URL. Với HTML attribute, hãy để template engine xử lý escaping sau khi URL được xây hợp lệ.

## 7. Số, ngày giờ và danh sách ở ranh giới

### 7.1. Số lượng và số tiền

Các trường hợp nên thử gồm `0`, `1`, số âm, số rất lớn, tiền có phần thập phân, giá trị thiếu và các kiểu định dạng số theo locale. Một giá trị hợp lệ ở nghiệp vụ này có thể là lỗi ở nghiệp vụ khác: số lượng `0` hợp lệ với “không có thông báo”, nhưng email xác nhận đơn hàng trống có thể cần bị từ chối.

Ví dụ định dạng theo locale trước khi đưa giá trị vào template:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat formatter =
    NumberFormat.getCurrencyInstance(Locale.forLanguageTag("vi-VN"));

String amountText =
    formatter.format(new BigDecimal("1234567.89"));
```

Cần định nghĩa rõ currency, số chữ số thập phân và quy tắc làm tròn theo nghiệp vụ. Đừng để template tự quyết ý nghĩa của số tiền. Kiểm tra **chuỗi cuối cùng sau render** để tránh các lỗi như `null ₫`, dấu phân cách sai hoặc cột giá bị tràn.

### 7.2. Ngày giờ và múi giờ

Thử thời điểm gần 23:59/00:00, cuối tháng, 29/2 năm nhuận, khác múi giờ hoặc thời điểm thiếu. Nếu lưu sự kiện bằng `Instant`, nên định dạng sang múi giờ của người nhận trước khi render:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Instant eventTime = Instant.parse("2026-11-12T08:30:00Z");

String formattedTime = DateTimeFormatter
    .ofPattern("dd/MM/yyyy HH:mm", Locale.forLanguageTag("vi-VN"))
    .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .format(eventTime);
```

Nếu thư liên quan lịch hẹn, phải làm rõ múi giờ để người dùng không hiểu nhầm. Tránh dùng thời gian hệ thống tại lúc render một cách vô thức vì cùng job có thể hiển thị thời điểm khác khi retry.

### 7.3. Danh sách rỗng, một phần tử và rất dài

| Dữ liệu | Hành vi cần thiết kế |
|---|---|
| `items == null` | Chuẩn hóa hoặc báo lỗi tùy hợp đồng dữ liệu. |
| `items.isEmpty()` | Hiển thị thông báo rỗng, không để bảng vô nghĩa. |
| Một item | Không thừa dấu phẩy, tiền tố hoặc sai số ít. |
| Nhiều item | Các dòng có dữ liệu và escaping đúng. |
| Hàng trăm item | Giới hạn danh sách, tóm tắt + link xem toàn bộ. |
| Tên sản phẩm chứa HTML | Render như văn bản, không tạo phần tử mới. |

Ví dụ Thymeleaf:

```html
<p th:if="${itemsEmpty}">
  Không có sản phẩm nào cần hiển thị.
</p>

<table th:unless="${itemsEmpty}" role="presentation">
  <tr th:each="item : ${items}">
    <td th:text="${item.name}">Tên sản phẩm</td>
    <td th:text="${item.formattedPrice}">0 ₫</td>
  </tr>
</table>
```

Để tránh tạo email hàng nghìn dòng, giới hạn dữ liệu trước render theo chính sách và cung cấp link đến trang chi tiết.

## 8. Kiểm tra cấu trúc HTML sau khi render

Khi cần assertions có ý nghĩa, có thể dùng **HTML parser**, chẳng hạn Jsoup trong môi trường test, rồi kiểm tra DOM thay vì so sánh nguyên chuỗi HTML.

Các điều kiện thường hữu ích:

- Có nội dung `html`/`body`, tiêu đề và nội dung nghiệp vụ bắt buộc.
- CTA là thẻ `a` với `href` đúng và nhãn dễ hiểu.
- Không còn placeholder `th:text`, `th:href`, `${...}` hoặc `{{...}}` chưa được render ở nơi đáng lẽ phải xử lý.
- Không có phần tử hoặc thuộc tính nguy hiểm được tạo bởi dữ liệu người dùng.
- Chỉ xuất hiện nhánh nội dung điều kiện tương ứng với dữ liệu.
- Các ảnh có `alt` và `src` có ý nghĩa.
- Link dùng host được phép, không chuyển sang môi trường test nhầm.
- Text quan trọng không rỗng hoặc bị cắt vì xử lý lỗi.

**Phải phân biệt HTML source với text content đã parse.** Chuỗi `A&B` có thể hiện trong source như `A&amp;B`, nhưng sau parse người đọc thấy `A&B`. Muốn kiểm tra escaping thì xem source; muốn kiểm tra nội dung người dùng thấy thì đọc text node; muốn kiểm tra an toàn cấu trúc thì xem những phần tử/attribute thực sự có mặt.

Chỉ tìm `"<script>"` trong chuỗi không phải cách chứng minh an toàn hoàn chỉnh. Cần escaping đúng ngữ cảnh, URL validation, template được kiểm soát, và sanitization bằng allowlist khi có yêu cầu nhận rich HTML.

## 9. Kiểm thử renderer bằng JUnit

Với `spring-boot-starter-test`, có thể thực thi template thật trong test mà **không gửi SMTP**. Mục tiêu là test logic render riêng, sau đó có thêm các test MIME/client ở mức khác.

### 9.1. ParameterizedTest cho nhiều đầu vào

Ví dụ một test class dùng renderer của mục 4:

```java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.mail.host=localhost",
    "spring.mail.port=1025"
})
class AccountEmailRendererTest {

    @Autowired
    AccountEmailRenderer renderer;

    static Stream<Arguments> edgeNames() {
        return Stream.of(
            Arguments.of((Object) null),
            Arguments.of(""),
            Arguments.of("   "),
            Arguments.of("Nguyễn Thị Ánh"),
            Arguments.of("日本語 😊"),
            Arguments.of("A&B <Quý khách>"),
            Arguments.of("<script>alert(1)</script>"),
            Arguments.of("A".repeat(300))
        );
    }

    @ParameterizedTest
    @MethodSource("edgeNames")
    void renderSupportsBoundaryNames(String name) {
        RenderedEmail result = renderer.render(
            name, "safe-test-token", 0
        );

        String html = result.htmlText();

        assertThat(html).contains("<html");
        assertThat(html).contains("Xác minh tài khoản");
        assertThat(html).doesNotContain("<script>alert(1)</script>");
        assertThat(html).doesNotContain("th:text=");
        assertThat(html).doesNotContain("th:href=");
        assertThat(html).contains(
            "https://accounts.example.com/verify"
        );
        assertThat(result.plainText()).contains(
            "Vui lòng xác minh tài khoản"
        );
    }
}
```

Ở đây Spring tạo `SpringTemplateEngine` và renderer; không gọi `AccountVerificationMailService.send(...)` nên không cần máy chủ SMTP thật. Giá trị token giả chỉ dùng trong test.

### 9.2. Test fallback và escaping riêng

Các phương thức dưới đây có thể đặt cùng class `AccountEmailRendererTest`:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

@Test
void blankNameUsesFallback() {
    RenderedEmail result = renderer.render(
        "  ", "demo-token", 0
    );

    assertThat(result.htmlText())
        .contains("<span>bạn</span>");
    assertThat(result.plainText())
        .contains("Xin chào, bạn!");
}

@Test
void htmlLikeNameIsEscaped() {
    RenderedEmail result = renderer.render(
        "<script>alert(1)</script>", "demo-token", 1
    );

    assertThat(result.htmlText())
        .doesNotContain("<script>alert(1)</script>");
    assertThat(result.htmlText())
        .contains("&lt;script&gt;");
}
```

Test trên chỉ minh họa một số khẳng định cụ thể; với nội dung HTML phong phú nên bổ sung kiểm tra DOM. Đừng dựa duy nhất vào chuỗi đã escape vì nhiều cách biểu diễn entity có thể tương đương về nội dung.

### 9.3. Test dữ liệu bắt buộc không hợp lệ

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;

@Test
void missingTokenIsRejected() {
    assertThatThrownBy(
        () -> renderer.render("An", "", 0)
    ).isInstanceOf(IllegalArgumentException.class);
}

@Test
void negativeNotificationCountIsRejected() {
    assertThatThrownBy(
        () -> renderer.render("An", "demo-token", -1)
    ).isInstanceOf(IllegalArgumentException.class);
}
```

Như vậy, dữ liệu biên có thể được kiểm tra ở hai nhóm: **đầu vào hợp lệ nhưng khó render** và **đầu vào không hợp lệ phải bị từ chối**.

### 9.4. Snapshot, DOM assertion và visual test

| Chiến lược | Mạnh ở đâu? | Giới hạn |
|---|---|---|
| Assert text/DOM/link | Đúng nội dung, escaping và cấu trúc | Cần xác định các điều kiện quan trọng. |
| HTML snapshot/golden file | Phát hiện thay đổi lớn của template | Dễ nhiễu do whitespace, timestamp và token động. |
| Screenshot diff | Phát hiện lệch bố cục | Cần renderer/môi trường hiển thị ổn định. |
| Email-client preview/test inbox | Đánh giá tương thích Gmail/Outlook/mobile | Tốn công hơn, có thể cần công cụ chuyên dụng. |

Nếu dùng snapshot, cố định clock, locale, timezone, token giả và input để kết quả tái lập được. Không lưu snapshot chứa thông tin cá nhân hoặc token thật vào repository.

## 10. Kiểm tra MIME sau khi render

HTML đúng về mặt string vẫn cần được Jakarta Mail đóng gói đúng:

- `Content-Type: text/html; charset=UTF-8` cho phần HTML.
- `text/plain` là bản thay thế đủ thông tin.
- `multipart/alternative` chứa plain và HTML khi gửi cùng nội dung ở hai dạng.
- `multipart/related` cho HTML tham chiếu tài nguyên inline bằng `cid:...`.
- `multipart/mixed` khi có attachment độc lập.
- Kích thước thông điệp sau MIME encoding phải phù hợp giới hạn SMTP.

Ví dụ:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
    message, true, "UTF-8"
);

helper.setFrom("no-reply@example.com");
helper.setTo(recipient);
helper.setSubject("Xác nhận");
helper.setText(plainText, htmlText);

mailSender.send(message);
```

Nếu HTML dùng:

```html
<img src="cid:brand-logo" alt="Logo thương hiệu">
```

Thì phần inline cần được thêm **sau** khi đặt text:

```java
helper.setText(plainText, htmlText);
helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

Một MIME tree thường có dạng:

```text
multipart/related
├── multipart/alternative
│   ├── text/plain
│   └── text/html (src="cid:brand-logo")
└── image/png (Content-ID: <brand-logo>)
```

Những dữ liệu biên của MIME bao gồm logo thiếu, CID không khớp, hình JPEG gắn sai Content-Type, nguồn `InputStream` chỉ đọc được một lần, file quá lớn hoặc việc gọi `setText(...)` thêm một lần sau khi `addInline(...)`.

**SMTP chấp nhận email không có nghĩa ảnh inline hiển thị đúng.** Khi gặp lỗi, xem raw MIME của thư nhận và đối chiếu `Content-ID` với `cid:...` trong HTML.

## 11. Kiểm tra hiển thị trên email client

HTML parser có thể xác nhận tài liệu hợp lệ nhưng Gmail, Outlook hoặc ứng dụng di động vẫn hiển thị khác nhau. Các tình huống cần xem:

| Tình huống | Điểm cần quan sát |
|---|---|
| Desktop và mobile | Bảng, đoạn text và CTA không bị cắt/tràn. |
| Màn hình hẹp 320–375px | Tên dài, liên kết dài không làm email cuộn ngang bất hợp lý. |
| Images blocked | Thông điệp chính vẫn đọc được, `alt` có ý nghĩa. |
| Dark mode | Tương phản chữ/nền, logo không biến mất. |
| Tăng cỡ chữ | Không có vùng nội dung đè lên nút. |
| Plain-text only | Link và thông tin nghiệp vụ vẫn đầy đủ. |
| Ngôn ngữ RTL | Dấu câu, số và URL không làm thông điệp khó hiểu. |
| CSS bị hạn chế | Table, inline styles và fallback vẫn hoạt động hợp lý. |
| Nội dung dài | CTA hoặc thông báo bắt buộc không bị ẩn sau vùng rút gọn. |

Để tăng khả năng tương thích:
- Ưu tiên HTML email đơn giản, cấu trúc table khi phù hợp và CSS inline có chủ đích.
- Không phụ thuộc JavaScript.
- Đặt `alt` cho ảnh; không để thông tin quan trọng chỉ trong hình ảnh.
- Dùng bản `text/plain` đầy đủ.
- Thử trên những mail client thực sự phổ biến với người nhận của sản phẩm.

Không có unit test chuỗi nào mô phỏng đầy đủ cơ chế render của tất cả mail client.

## 12. Kích thước HTML và giới hạn vận hành

Dữ liệu biên còn gồm **khối lượng**:
- 1.000 sản phẩm tạo hàng nghìn thẻ `tr`;
- 20 ảnh inline tăng dung lượng MIME đáng kể;
- một mô tả hoặc URL dài hàng nghìn ký tự;
- nội dung người dùng lên đến hàng trăm KB.

Hệ quả có thể là render chậm, sử dụng nhiều RAM, email vượt giới hạn SMTP, bị client rút gọn hoặc người dùng không nhìn thấy CTA quan trọng.

Cách thiết kế:
1. Giới hạn số item đưa vào template theo yêu cầu nghiệp vụ.
2. Tóm tắt danh sách dài và cung cấp link xem đầy đủ.
3. Tối ưu hình ảnh, attachment và dung lượng phần MIME.
4. Không nhúng ảnh Base64 khổng lồ trực tiếp vào HTML khi client có thể không hỗ trợ tốt.
5. Tách timeout/retry của bước lấy dữ liệu và bước gửi SMTP.
6. Đo kích thước **sau khi mã hóa MIME**, không chỉ số ký tự HTML.

Không nên cắt bỏ thông tin bắt buộc để giảm kích thước thư; hãy chọn bố cục gọn và đường dẫn xem chi tiết phù hợp.

## 13. Phân loại lỗi theo tầng

| Triệu chứng | Tầng cần xem trước | Hướng điều tra |
|---|---|---|
| Chữ `null` hoặc placeholder trong email | Model/template | Fallback, binding và điều kiện hiển thị. |
| Dữ liệu tạo thẻ HTML bất thường | Escaping/security | `th:text`, tránh `th:utext` với input không tin cậy. |
| CTA trỏ sai host | URL construction | Base URL, allowlist, query encoding. |
| Tiếng Việt bị lỗi | Render/MIME | UTF-8, Content-Type, template encoding. |
| Ảnh inline không hiện | MIME/client | CID, Content-ID, resource, multipart mode. |
| Bảng tràn trên mobile | HTML/CSS/client | Chiều rộng, chuỗi dài, bố cục. |
| SMTP AUTH thất bại | Transport/secret | Credential, cổng và TLS. |
| SMTP trả lỗi message quá lớn | MIME/transport | Tổng dung lượng ảnh/attachment. |
| SMTP đã nhận nhưng Inbox không thấy | Delivery | Event provider, bounce, spam filtering. |

Hãy xác định **lỗi nằm ở tầng nào** trước khi thay đổi. Sửa SMTP password không giải quyết lỗi HTML escaping; đổi template không giải quyết lỗi mạng.

## 14. Bộ ca kiểm tra mẫu trước khi đưa template vào sử dụng

| Dữ liệu | Hành động | Kỳ vọng |
|---|---|---|
| Tên bình thường và đủ field | Render | Nội dung, CTA và text đúng. |
| Tên null/rỗng | Render | Fallback thay vì `null` hoặc lời chào rỗng. |
| Tên chứa `<script>` | Render + inspect DOM | Dữ liệu escape, không tạo script. |
| Tiếng Việt/emoji | Render + MIME/test inbox | Không mất ký tự. |
| Tên 300 ký tự | Xem trên mobile | Không tràn khung hoặc che nút. |
| Count = 0 | Render | Đúng nhánh thông báo rỗng. |
| Count = -1 | Gọi renderer | Từ chối dữ liệu sai. |
| Token chứa `+`, `/`, `=` | Render + parse href | Query encode đúng, giữ giá trị. |
| Danh sách rỗng | Render | Không tạo bảng trống vô nghĩa. |
| Danh sách dài | Render + test inbox | Giới hạn/tóm tắt có chủ đích. |
| CID không khớp | MIME inspection | Phát hiện resource không liên kết. |
| Ảnh bị chặn | Xem thư nhận | Thông điệp vẫn hiểu được. |
| Chỉ xem plain text | Xem `text/plain` | Có nội dung và đường dẫn cần thiết. |

Có thể lưu snapshot/ảnh chụp thử nghiệm **chỉ với dữ liệu giả** và so sánh khi template thay đổi. Không đưa email thật, URL có token thật hoặc thông tin khách hàng vào artifact test được chia sẻ.

## 15. Những hiểu lầm phổ biến

**“Template render không lỗi là email đúng.”** Không. HTML có thể hợp cú pháp nhưng thiếu dữ liệu bắt buộc, link sai hoặc bố cục không dùng được.

**“Escape HTML là đủ để URL an toàn.”** Không. URL phải được xây từ đích tin cậy hoặc validate scheme/host, ngoài escaping attribute.

**“Dữ liệu đến từ database thì dùng th:utext được.”** Không. Database có thể chứa dữ liệu người dùng và nguồn ngoài, không mặc nhiên trở thành HTML được tin cậy.

**“Thêm UTF-8 vào template là đủ.”** Chưa chắc. Cần xem cả render và phần MIME charset/encoding.

**“Test bằng browser sẽ giống mọi email client.”** Không. Email client có chính sách HTML/CSS riêng.

**“JavaMailSender không ném lỗi tức HTML hiển thị đẹp.”** Không. Gửi SMTP và render phía nhận là các giai đoạn khác nhau.

**“Snapshot giống hôm trước là tất cả an toàn.”** Không. Snapshot cần đi cùng kiểm tra nghĩa nội dung, URL, DOM và các ca biên.

## 16. Bài tập thực hành

### Bài 1: Fallback tên hiển thị
Thử `null`, `""`, `"   "` và `"Nguyễn An"`. Viết assertions xác nhận giá trị rỗng thành `"bạn"` và tên hợp lệ hiển thị đúng sau render.

### Bài 2: Escaping
Template dùng `th:utext` với dữ liệu tên người dùng. Đưa chuỗi `<img src=x onerror=alert(1)>` vào model, rồi thay bằng `th:text` và giải thích vì sao tên người dùng cần được hiển thị như văn bản.

### Bài 3: Kiểm tra CTA
Token giả là `a+b/c==`. Render URL từ HTTPS base cố định, parse thuộc tính `href` và xác minh query encode đúng. Không log token thật.

### Bài 4: Số ở biên
Thử `notificationCount=0`, `1`, `100` và `-1`. Xác nhận nhánh thông báo đúng và số âm bị từ chối.

### Bài 5: Unicode và độ dài
Thử tên tiếng Việt, tiếng Nhật, emoji và 300 ký tự. So sánh `String.length()` và `codePointCount(...)`; nêu lý do cắt theo code point vẫn có thể chia một grapheme cluster phức tạp.

### Bài 6: Danh sách và bảng
Khi danh sách sản phẩm rỗng, hiển thị thông báo thay bảng. Khi có một sản phẩm tên `A&B <C>`, hiển thị tên đã escape và giá định dạng đúng.

### Bài 7: MIME/CID
HTML dùng `src="cid:receipt-logo"` nhưng helper gọi `addInline("company-logo", ...)`. Sửa ID và giải thích vì sao kiểm tra HTML string chưa đủ, còn phải kiểm tra các part của MIME.

### Bài 8: Ma trận kiểm tra
Thiết kế bộ test cho email đơn hàng gồm các trường hợp tên, giá, timezone, danh sách rỗng/dài, injection, URL chứa ký tự đặc biệt và ảnh bị chặn. Mỗi ca ghi rõ **input, output kỳ vọng và tầng kiểm tra** (model, rendered HTML, MIME hoặc client).

## 17. Tổng kết

**Kiểm tra HTML sau khi render bằng dữ liệu biên** giúp phát hiện lỗi mà việc xem template hoặc chỉ gửi một email mẫu không thể phát hiện: thiếu giá trị, escaping sai, Unicode lỗi, URL không hợp lệ, bố cục tràn, danh sách quá lớn hoặc MIME inline không liên kết đúng.

Với Spring Framework Mail, nên **tách renderer khỏi sender**: validate dữ liệu → normalize/format → render HTML và plain text → kiểm tra đầu ra → tạo `MimeMessage` → gửi qua `JavaMailSender`. Kết hợp **JUnit cho logic render**, **HTML parser cho DOM/URL**, **MIME inspection cho encoding và CID**, và **test inbox cho khả năng hiển thị trên client mục tiêu**. Đó là cách kiểm soát chất lượng nội dung email trước khi SMTP bắt đầu vận chuyển thông điệp.


