# Escape HTML, URL và text theo ngữ cảnh

## 1. Vì sao phải escape theo đúng ngữ cảnh?

Trong **Spring Framework Mail**, ứng dụng thường lấy dữ liệu từ người dùng hoặc hệ thống nghiệp vụ rồi đưa vào template email: tên người nhận, tên sản phẩm, mã đơn hàng, liên kết xác minh, tiêu đề và nội dung thông báo. Nếu chèn dữ liệu động vào HTML một cách trực tiếp, ký tự đặc biệt có thể làm hỏng cấu trúc email hoặc biến dữ liệu thành markup ngoài ý muốn.

Ví dụ:

~~~java
String displayName = "<img src=x onerror=alert(1)>";
String html = "<p>Xin chào " + displayName + "</p>";
~~~

Chuỗi `displayName` vốn chỉ là dữ liệu, nhưng sau khi nối vào HTML, nó trở thành một thẻ HTML. Mail client thường lọc HTML nguy hiểm, nhưng **không được dựa vào bộ lọc của mail client để bảo vệ hệ thống tạo email**.

Một ví dụ khác là URL:

~~~java
String token = "abc&next=https://attacker.example";
String href = "https://accounts.example.com/verify?token=" + token;
String html = "<a href=\"" + href + "\">Xác minh</a>";
~~~

Ký tự `&` trong token có thể bị hiểu là dấu phân cách query parameter. Nếu URL được đặt vào thuộc tính `href` mà không escape HTML attribute, dấu nháy hoặc ký tự đặc biệt có thể làm thay đổi markup.

Vì vậy cần hiểu **contextual output encoding** (mã hóa đầu ra theo ngữ cảnh): cùng một giá trị đầu vào có thể cần cách xử lý khác nhau tùy nơi nó được đưa vào:

- HTML text node: nội dung giữa hai thẻ.
- HTML attribute: giá trị của `href`, `title`, `alt` hoặc thuộc tính khác.
- URL component: một đoạn path hoặc một query parameter.
- Plain text email: nội dung văn bản thuần, không phải HTML.
- Các ngữ cảnh khác như CSS hoặc JavaScript: cần quy tắc riêng; tốt nhất tránh đưa dữ liệu không tin cậy vào các ngữ cảnh này.

> **Nguyên tắc:** Hãy xác định nơi dữ liệu sẽ xuất hiện, kiểm tra/chuẩn hóa theo quy tắc của nơi đó, rồi encode ở bước xuất cuối. Không có một hàm “escape tất cả” dùng an toàn cho mọi ngữ cảnh.

## 2. Phân biệt escape, encode, validate và sanitize

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **Escape / output encoding** | Biểu diễn dữ liệu sao cho parser của ngữ cảnh đích không nhầm dữ liệu với cú pháp | `<` thành `&lt;` trong HTML text |
| **URL component encoding** | Mã hóa ký tự của một thành phần URL theo quy tắc URI | Giá trị query chứa `&` được mã hóa để không tạo tham số mới |
| **Validation** | Kiểm tra dữ liệu có nằm trong tập giá trị hoặc chính sách được phép không | Chỉ chấp nhận link `https` tới domain được phê duyệt |
| **Normalization** | Đưa dữ liệu về dạng chuẩn theo yêu cầu nghiệp vụ | Chuẩn hóa line ending hoặc định dạng mã đơn hàng |
| **Sanitization** | Loại bỏ hoặc biến đổi cấu trúc không được phép trong nội dung có markup | Cho phép một tập HTML an toàn khi sản phẩm hỗ trợ rich text |

URL encode một chuỗi không có nghĩa URL đó an toàn để điều hướng. Chuỗi `javascript:alert(1)` vẫn là scheme không được phép dù ký tự đã được encode theo một cách nào đó. Tương tự, HTML escape một đoạn HTML không phải cách sanitize nếu mục tiêu là cho phép một số thẻ như `<strong>` và `<a>` được render.

### 2.1. Escape dữ liệu ở thời điểm xuất

1. Lưu dữ liệu nghiệp vụ ở dạng dữ liệu bình thường, không lưu phiên bản HTML đã escape làm dữ liệu gốc.
2. Khi dựng template, xác định context của từng biến.
3. Dùng template engine hoặc encoder phù hợp để encode đúng context.
4. Không escape lại lần nữa nếu template engine đã tự động escape.

Ví dụ dữ liệu gốc:

~~~text
R&D <North>
~~~

Khi đưa vào HTML text, nó có thể được serialize thành:

~~~html
R&amp;D &lt;North&gt;
~~~

Người nhận vẫn thấy `R&D <North>`. Việc lưu luôn chuỗi `R&amp;D &lt;North&gt;` làm dữ liệu gốc dễ dẫn đến double escaping và khó tái sử dụng cùng dữ liệu ở plain text, CSV hoặc giao diện khác.

## 3. Escape HTML text node

**HTML text context** là vùng nội dung nằm giữa thẻ mở và thẻ đóng:

~~~html
<p>Giá trị động xuất hiện ở đây</p>
~~~

Các ký tự quan trọng cần được biểu diễn an toàn:

| Ký tự dữ liệu | Biểu diễn HTML thường dùng |
| --- | --- |
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | `&gt;` |
| Dấu nháy kép `"` | Có thể biểu diễn `&quot;` |
| Dấu nháy đơn `'` | Có thể biểu diễn `&#39;` hoặc entity tương ứng |

Ví dụ:

~~~text
Lan <Admin> & "Support"
~~~

được đưa vào HTML dưới dạng:

~~~html
<p>Lan &lt;Admin&gt; &amp; &quot;Support&quot;</p>
~~~

Mail client hiển thị ký tự gốc dưới dạng văn bản; chúng không còn được parser hiểu là thẻ HTML hay cú pháp.

### 3.1. Dùng Thymeleaf để escape text tự động

Nếu email được render bằng Thymeleaf, ưu tiên `th:text` cho dữ liệu text:

~~~html
<p th:text="${displayName}">
  Tên người nhận
</p>
~~~

`th:text` thay nội dung phần tử bằng giá trị đã được escape HTML. Nếu `displayName` là `<img src=x onerror=alert(1)>`, chuỗi đó được hiển thị như văn bản thay vì tạo thẻ ảnh.

Ví dụ template:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <p>Xin chào <strong th:text="${displayName}">bạn</strong>,</p>
  <p>
    Đơn hàng
    <span th:text="${orderNumber}">A-100</span>
    đã được xác nhận.
  </p>
</body>
</html>
~~~

Đây là cách phù hợp cho tên, mã đơn hàng và chuỗi nghiệp vụ thông thường. Không gọi thêm hàm escape trong Java rồi đưa kết quả vào `th:text`, vì có thể bị **escape hai lần**.

### 3.2. Dùng encoder rõ ràng khi tự dựng HTML

Nếu code Java bắt buộc phải ghép một đoạn HTML, hãy dùng thư viện encoder chuyên dụng. Ví dụ với **OWASP Java Encoder**:

~~~java
import org.owasp.encoder.Encode;

String displayName = "<img src=x onerror=alert(1)>";
String safeText = Encode.forHtml(displayName);
String html = "<p>Xin chào " + safeText + "</p>";
~~~

`Encode.forHtml(...)` dành cho HTML text context. Không nên tự viết hàm thay thế vài ký tự bằng `String.replace(...)` rồi dùng như encoder hoàn chỉnh: thứ tự thay thế, ký tự quote, Unicode và các ngữ cảnh khác nhau dễ bị bỏ sót.

## 4. Escape HTML attribute

**HTML attribute context** xuất hiện khi dữ liệu được đưa vào giá trị thuộc tính:

~~~html
<a href="...">Mở liên kết</a>
<img src="..." alt="...">
<td title="...">...</td>
~~~

Giá trị thuộc tính nên luôn được đặt trong dấu nháy. Nếu dữ liệu chứa dấu nháy kép và được nối trực tiếp:

~~~java
String title = "\" onmouseover=\"alert(1)";
String html = "<a title=\"" + title + "\">Xem</a>";
~~~

chuỗi có thể kết thúc thuộc tính `title` sớm và thêm thuộc tính khác. Hãy encode cho **HTML attribute context**:

~~~java
String safeTitle = Encode.forHtmlAttribute(title);
String html = "<a title=\"" + safeTitle + "\">Xem</a>";
~~~

Encoder biểu diễn dấu nháy và ký tự đặc biệt bằng entity thích hợp. Luôn dùng dấu nháy quanh giá trị attribute ngay cả khi dữ liệu hiện tại có vẻ chỉ chứa chữ và số.

### 4.1. Thymeleaf tự escape attribute thông thường

~~~html
<a th:title="${displayTitle}">Xem thông tin</a>
<img th:alt="${imageDescription}" src="/mail/logo.png">
~~~

Thymeleaf xử lý giá trị attribute qua cơ chế escape của template engine. Không nối chuỗi vào thuộc tính HTML trong Java nếu có thể dùng template engine với binding an toàn.

### 4.2. HTML attribute encoding không thay thế validation

~~~html
<a href="...">...</a>
<div style="...">...</div>
<button onclick="...">...</button>
~~~

`href` có ngữ nghĩa điều hướng URL; `style` là CSS; `onclick` là JavaScript. Mỗi ngữ cảnh có parser và rủi ro riêng. Một chuỗi được encode cho HTML attribute vẫn có thể mang scheme không an toàn trong `href` hoặc giá trị CSS nguy hiểm trong `style`. Không đưa dữ liệu không tin cậy vào event handler hoặc style động.

## 5. URL encoding: mã hóa từng thành phần

URL có cấu trúc gồm scheme, authority/host, path, query và fragment. Khi dữ liệu động nằm trong URL, phải xác định nó là **path segment** hay **query parameter value**.

~~~text
https://accounts.example.com/verify?token=abc123
                                      ^^^^^^
                                      query parameter value
~~~

Nếu token có ký tự `&`, `=`, `+`, khoảng trắng hoặc Unicode, nối chuỗi trực tiếp có thể thay đổi ý nghĩa URL. Hãy encode **component** bằng API URI builder:

~~~java
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;

String token = "abc&next=hello world";

String verificationUrl = UriComponentsBuilder
        .fromUriString("https://accounts.example.com/verify")
        .queryParam("token", "{token}")
        .encode()
        .buildAndExpand(Map.of("token", token))
        .toUriString();
~~~

`{token}` là biến URI template. `encode()` và `buildAndExpand(...)` mã hóa giá trị biến theo quy tắc component thích hợp thay vì để `&` trong token trở thành query parameter mới.

Với dữ liệu nằm trong path, dùng path segment thay vì nối vào path:

~~~java
String documentId = "report/2026 & final";

String documentUrl = UriComponentsBuilder
        .fromUriString("https://files.example.com")
        .pathSegment("documents", "{id}")
        .encode()
        .buildAndExpand(Map.of("id", documentId))
        .toUriString();
~~~

`pathSegment` coi giá trị là một segment; dấu `/` nằm trong dữ liệu không được tự biến thành một cấp path mới.

### 5.1. URL encode không xác nhận đích đến an toàn

Ví dụ các giá trị cần xem xét:

~~~text
javascript:alert(1)
https://trusted.example/path
https://trusted.example.attacker.invalid/path
//attacker.invalid/path
data:text/html,...
~~~

Chỉ encode URL **không** quyết định URL nào được phép sử dụng. Nếu ứng dụng gửi email có link, cần **validation/allowlist** cho destination:

- Chỉ chấp nhận scheme được phép, thường là `https`; chỉ cho `http` nếu có yêu cầu rõ ràng.
- Kiểm tra hostname chính xác theo allowlist, không dùng so sánh chuỗi kiểu `contains("trusted.example")`.
- Xem xét port, user-info, fragment và URL dạng protocol-relative nếu chúng ảnh hưởng chính sách.
- Nếu link phải trỏ tới domain của hệ thống, tạo từ base URL tin cậy trong cấu hình thay vì nhận toàn bộ URL từ client.
- Không cho phép scheme như `javascript:`, `data:` hoặc `file:` làm đích link.

Ví dụ kiểm tra URL đã parse:

~~~java
import java.net.URI;
import java.util.Set;

private static final Set<String> ALLOWED_HOSTS =
        Set.of("accounts.example.com", "www.example.com");

static URI requireAllowedHttpsUrl(String value) {
    URI uri = URI.create(value);
    String scheme = uri.getScheme();
    String host = uri.getHost();

    if (!"https".equalsIgnoreCase(scheme)
            || host == null
            || !ALLOWED_HOSTS.contains(host.toLowerCase())) {
        throw new IllegalArgumentException("URL destination is not allowed");
    }
    if (uri.getUserInfo() != null) {
        throw new IllegalArgumentException("URL user-info is not allowed");
    }
    return uri;
}
~~~

Đây là allowlist tối giản cho link HTTPS có host cố định. Hệ thống thật cần xác định thêm chính sách port, path, redirect và domain quốc tế hóa theo nghiệp vụ. Kiểm tra URL trong ứng dụng email chủ yếu ngăn gửi link tới đích ngoài ý muốn; nếu ứng dụng **fetch URL từ server**, còn phải xử lý rủi ro SSRF và kiểm tra DNS/IP/redirect riêng.

### 5.2. URL encoding và HTML attribute encoding là hai bước khác nhau

Khi tạo liên kết trong HTML email:

1. **Validate destination**: scheme/host/path có được phép không?
2. **Build URL**: đưa từng giá trị vào đúng path/query component bằng URI builder.
3. **HTML attribute encode**: khi đặt URL hoàn chỉnh vào `href`, encode nó cho HTML attribute context.

Ví dụ dùng OWASP Java Encoder:

~~~java
String url = verificationUrl; // Base URL tin cậy, query param đã encode.
String safeHref = Encode.forHtmlAttribute(url);
String html = "<a href=\"" + safeHref + "\">Xác minh tài khoản</a>";
~~~

**URL component encoding** xử lý cấu trúc URL; **HTML attribute encoding** bảo vệ cú pháp markup. Một bước không thay thế bước còn lại.

### 5.3. Không HTML-escape trước rồi mới URL-encode tùy tiện

~~~text
token = abc&next=home
~~~

Nếu HTML escape chuỗi trước, ta có `abc&amp;next=home`. Đưa chuỗi này vào query builder có thể khiến URL mang dữ liệu `&amp;` thay vì giá trị ban đầu `&`. Thứ tự đúng là **build/encode URL từ dữ liệu gốc trước**, rồi HTML attribute encode URL kết quả khi nhúng vào markup.

Trong template engine có xử lý URL expression và HTML attribute tự động, hãy để template engine làm cả hai bước theo API của nó; không tự encode trước biến rồi truyền vào biểu thức URL khác.

## 6. Dùng URL expression trong Thymeleaf email template

Thymeleaf có **link expressions** để tạo URL và gắn tham số:

~~~html
<a th:href="@{https://accounts.example.com/verify(token=${token})}">
  Xác minh tài khoản
</a>
~~~

Thymeleaf xây dựng URL từ biểu thức và mã hóa tham số theo cơ chế URL expression. Giá trị sau đó được ghi vào thuộc tính HTML qua cơ chế escape của template engine. Đây là cách tốt hơn việc nối chuỗi URL trong template.

Với URL đã được backend xây dựng và kiểm tra, có thể dùng:

~~~html
<a th:href="${verificationUrl}">Xác minh tài khoản</a>
~~~

Thymeleaf vẫn escape giá trị thuộc tính khi render, nhưng **không thay thế validation đích đến**. Nếu `verificationUrl` đến từ dữ liệu không tin cậy, backend phải kiểm tra scheme/host và chính sách link trước khi đưa vào model.

### 6.1. Ví dụ template hoàn chỉnh

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <p>
    Xin chào
    <strong th:text="${displayName}">bạn</strong>,
  </p>
  <p>Yêu cầu xác minh của bạn đã được tạo.</p>
  <p>
    <a th:href="@{https://accounts.example.com/verify(token=${token})}">
      Xác minh tài khoản
    </a>
  </p>
</body>
</html>
~~~

`displayName` là text nên dùng `th:text`. `token` được đặt vào query parameter qua URL expression. Host `accounts.example.com` là domain cố định do ứng dụng tin cậy xác định, không phải URL tùy ý từ người dùng.

Nếu email có cả HTML và plain text, hãy tạo hai nội dung có ý nghĩa tương đương. Bản plain có thể ghi URL đầy đủ, trong khi bản HTML dùng liên kết có nhãn:

~~~text
Xin chào Lan,

Xác minh tài khoản tại:
https://accounts.example.com/verify?token=...
~~~

Không nên chỉ gửi HTML rồi để client tự tạo bản text; kết quả chuyển đổi tự động có thể làm mất ngữ cảnh hoặc nhãn liên kết quan trọng.

## 7. Text trong email plain text: không HTML-escape

Một email `text/plain` không được phân tích như HTML. Vì vậy nếu nội dung người dùng là:

~~~text
R&D <North> "Support"
~~~

thì bản plain text nên giữ nguyên:

~~~text
R&D <North> "Support"
~~~

Không biến nó thành:

~~~text
R&amp;D &lt;North&gt; &quot;Support&quot;
~~~

Trong Spring Mail:

~~~java
helper.setText(plainText, false);
~~~

`false` khai báo body là plain text. Không cần gọi `Encode.forHtml(...)` cho `plainText`.

### 7.1. Tạo plain text và HTML từ cùng dữ liệu

~~~java
String displayName = "Lan <Admin>";
String verificationUrl = trustedVerificationUrl;

String plainText = """
        Xin chào %s,

        Xác minh tài khoản tại:
        %s
        """.formatted(displayName, verificationUrl);
~~~

Với plain text, dấu `<` trong tên người dùng chỉ là ký tự. URL vẫn cần được xây dựng/validate ở tầng URL; plain text không cần HTML attribute encoding.

Phần HTML phải encode riêng:

~~~java
String html = "<p>Xin chào "
        + Encode.forHtml(displayName)
        + "</p><p><a href=\""
        + Encode.forHtmlAttribute(verificationUrl)
        + "\">Xác minh tài khoản</a></p>";
~~~

`verificationUrl` được giả định đã được tạo từ base URL tin cậy và query parameters đã được encode. `Encode.forHtmlAttribute` chỉ xử lý bước nhúng URL vào HTML attribute.

### 7.2. Xử lý xuống dòng trong nội dung người dùng

Plain text giữ nguyên xuống dòng theo nội dung nghiệp vụ. HTML lại gom nhiều whitespace liên tiếp theo quy tắc hiển thị mặc định, nên cần chuyển đổi có kiểm soát:

~~~java
String normalized = userMessage
        .replace("\r\n", "\n")
        .replace('\r', '\n');

String escaped = Encode.forHtml(normalized);
String htmlBody = "<p style=\"white-space:pre-wrap;\">"
        + escaped
        + "</p>";
~~~

`white-space:pre-wrap` được dùng để giữ xuống dòng và khoảng trắng trong các client hỗ trợ. Nếu cần tương thích rộng hơn, có thể chuyển dấu xuống dòng thành `<br>` **sau khi đã escape phần text**, hoặc tạo từng đoạn `<p>` riêng. Không thay newline bằng HTML trước rồi escape toàn bộ, vì thẻ `<br>` do ứng dụng tạo cũng bị biến thành văn bản.

Một quy trình khác:

~~~java
String normalized = userMessage
        .replace("\r\n", "\n")
        .replace('\r', '\n');
String escaped = Encode.forHtml(normalized);
String htmlBody = "<p>" + escaped.replace("\n", "<br>") + "</p>";
~~~

`<br>` là markup cố định do ứng dụng tạo; phần text người dùng đã được escape trước. Đây là cách biểu diễn line break, không phải cho phép người dùng cung cấp HTML.

### 7.3. Text body khác email header

Đừng nhầm body plain text với các trường header như `Subject`, `From`, `To` hoặc `Reply-To`. Header có cú pháp riêng và có thể bị ảnh hưởng bởi ký tự xuống dòng.

Với tiêu đề lấy từ dữ liệu người dùng:

- Giới hạn độ dài theo nghiệp vụ.
- Loại bỏ hoặc từ chối ký tự điều khiển CR/LF nếu không được phép.
- Dùng API `MimeMessageHelper.setSubject(...)` hoặc API Jakarta Mail thay vì tự nối dòng raw header.
- Không đặt chuỗi tùy ý vào `addHeader(...)` mà không kiểm tra tên và giá trị header.

~~~java
static String requireSingleLineSubject(String value) {
    if (value == null || value.length() > 180
            || value.indexOf('\r') >= 0
            || value.indexOf('\n') >= 0) {
        throw new IllegalArgumentException("Invalid email subject");
    }
    return value;
}

helper.setSubject(requireSingleLineSubject(subject));
~~~

Đây là validation ví dụ; giới hạn độ dài và quy tắc nội dung cần được điều chỉnh theo sản phẩm. Jakarta Mail có xử lý header encoding và kiểm tra cú pháp riêng, nhưng kiểm tra dữ liệu nghiệp vụ trước khi đặt vào header vẫn cần thiết.

## 8. Không đưa dữ liệu không tin cậy vào CSS hoặc JavaScript

Escape HTML text hay HTML attribute không tự biến một giá trị thành CSS hoặc JavaScript an toàn. Tránh các ví dụ:

~~~java
String html = "<div style=\"color:" + userColor + "\">Thông báo</div>";
String html2 = "<button onclick=\"" + userAction + "\">Mở</button>";
~~~

`userColor` được đặt vào **CSS value context**; `userAction` được đặt vào **JavaScript context**. Chỉ HTML-escape hai chuỗi này không giải quyết đầy đủ parser của CSS/JavaScript.

### 8.1. Dùng tập giá trị được phép thay cho CSS động

~~~java
enum StatusStyle {
    SUCCESS("color:#166534; background-color:#dcfce7;"),
    WARNING("color:#92400e; background-color:#fef3c7;"),
    ERROR("color:#991b1b; background-color:#fee2e2;");

    private final String inlineStyle;

    StatusStyle(String inlineStyle) {
        this.inlineStyle = inlineStyle;
    }

    public String inlineStyle() {
        return inlineStyle;
    }
}
~~~

Ứng dụng parse giá trị đầu vào thành enum hợp lệ rồi chọn style do code kiểm soát. Nếu giá trị không khớp enum, dùng fallback an toàn hoặc từ chối request.

Trong template, có thể chọn class cố định:

~~~html
<p th:classappend="${status == 'SUCCESS'} ? 'status-success' : 'status-neutral'"
   th:text="${statusLabel}">
  Trạng thái
</p>
~~~

`statusLabel` vẫn là text và dùng `th:text`. Lớp CSS được chọn từ các nhánh do ứng dụng định nghĩa, không nhận trực tiếp chuỗi CSS tùy ý.

### 8.2. Tránh event handler và JavaScript trong email

Không tạo email dựa trên:

~~~html
<a href="#" onclick="doSomething()">Bấm tại đây</a>
<script>...</script>
~~~

Nhiều mail client loại bỏ script/event handler. Email nên dùng liên kết HTTPS tới một trang web thực hiện hành động sau khi người dùng xác thực phù hợp. Không đưa dữ liệu động vào script, event handler hoặc thuộc tính CSS để cố tạo tương tác.

## 9. Khi nào cần sanitize HTML thay vì escape?

Có hai yêu cầu khác nhau:

**Yêu cầu A — Hiển thị dữ liệu như văn bản.** Nếu người dùng nhập `<strong>Xin chào</strong>` nhưng sản phẩm chỉ muốn hiển thị nguyên văn chuỗi đó, dùng HTML text escaping. Người nhận thấy dấu thẻ như một phần văn bản.

**Yêu cầu B — Cho phép một tập rich text.** Nếu sản phẩm cho phép người dùng định dạng chữ đậm, liên kết hoặc danh sách, HTML escape toàn bộ sẽ làm mất markup mong muốn. Khi đó cần **HTML sanitizer dựa trên allowlist** để giữ đúng các thẻ/thuộc tính/protocol được phép.

Một policy rich text có thể cho phép:

- Thẻ đơn giản như `p`, `strong`, `em`, `ul`, `ol` và `li`.
- Link `a` chỉ với thuộc tính `href` được kiểm tra.
- Một số thuộc tính định dạng cần thiết.
- Chỉ scheme URL được phép, thường là `https` hoặc `mailto` theo yêu cầu.

Nên loại bỏ script, event handler, iframe, object, form, CSS tùy ý và các thuộc tính không cần thiết. Thư viện như **OWASP Java HTML Sanitizer** hoặc **jsoup Safelist** có thể hỗ trợ xây dựng allowlist; cần cấu hình policy cụ thể, không bật chế độ cho phép mọi HTML.

### 9.1. Escape và sanitize cho ra kết quả khác nhau

Đầu vào:

~~~html
<p>Xin chào <strong>Lan</strong></p>
<script>alert(1)</script>
~~~

Nếu **escape toàn bộ** cho HTML text, người nhận thấy nguyên dấu thẻ như văn bản. Nếu **sanitize theo allowlist**, kết quả có thể giữ:

~~~html
<p>Xin chào <strong>Lan</strong></p>
~~~

và loại bỏ script. Cách thứ hai chỉ phù hợp khi nghiệp vụ chủ động cho phép rich text. Dữ liệu đã sanitize vẫn phải được đưa vào **đúng HTML body context**, không tái sử dụng nó làm giá trị attribute, URL, CSS hoặc JavaScript.

### 9.2. Thymeleaf th:text và th:utext

Trong Thymeleaf:

- `th:text` escape nội dung text.
- `th:utext` chèn nội dung **không escape** (unescaped text).

~~~html
<p th:text="${comment}">Nội dung bình luận</p>
<div th:utext="${sanitizedRichText}"></div>
~~~

`th:utext` chỉ được dùng nếu `sanitizedRichText` đã được xử lý bởi sanitizer có policy phù hợp và không bị sửa đổi sau bước sanitize. Không dùng `th:utext` với comment tùy ý do người dùng nhập.

**Sanitization không thay thế output encoding ở những context khác.** Một đoạn HTML an toàn trong body không tự động trở thành URL an toàn trong `href` hoặc CSS an toàn trong `style`.

## 10. Tích hợp template an toàn với JavaMailSender

Một service gửi email có thể chia trách nhiệm thành:

1. **Tầng nghiệp vụ** xác định người nhận, dữ liệu và quyền thực hiện hành động.
2. **Tầng URL** tạo liên kết từ base URL tin cậy và các component đã encode.
3. **Template engine** đặt dữ liệu vào đúng context và tự escape HTML text/attribute.
4. **Spring Mail** tạo MIME message và gửi HTML cùng plain text.

Ví dụ service dùng Thymeleaf:

~~~java
package com.example.mail;

import java.util.Locale;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class VerificationEmailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;

    public VerificationEmailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
    }

    public void send(
            String recipient,
            String displayName,
            String verificationUrl) throws MessagingException {

        // URL phải được tạo từ base URL tin cậy, query đã encode
        // và destination đã được kiểm tra.
        Context context = new Context(Locale.forLanguageTag("vi"));
        context.setVariable("displayName", displayName);
        context.setVariable("verificationUrl", verificationUrl);

        // Template dùng th:text và th:href; không dùng th:utext
        // cho dữ liệu text tùy ý.
        String html = templateEngine.process(
                "mail/verification", context);

        String plainText = """
                Xin chào %s,

                Xác minh tài khoản tại:
                %s
                """.formatted(displayName, verificationUrl);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Xác minh tài khoản");
        helper.setText(plainText, html);
        mailSender.send(message);
    }
}
~~~

Ví dụ cần cấu hình `TemplateEngine`, template resource, sender và địa chỉ gửi theo ứng dụng. `verificationUrl` phải được tạo/kiểm tra trước khi đưa vào context; `displayName` là text không tin cậy nên template dùng `th:text`. `MimeMessageHelper` không tự sanitize template và không tự xác nhận URL đích.

### 10.1. Template Thymeleaf tương ứng

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <p>
    Xin chào
    <strong th:text="${displayName}">bạn</strong>,
  </p>
  <p>Vui lòng xác minh địa chỉ email của bạn.</p>
  <p>
    <a th:href="${verificationUrl}">Xác minh tài khoản</a>
  </p>
</body>
</html>
~~~

Ở đây `th:text` escape `displayName` trong HTML text node; `th:href` ghi URL vào HTML attribute theo cơ chế escape của template engine. URL đã phải được backend xây dựng và kiểm tra. Nếu muốn tạo URL trực tiếp trong template, dùng link expression `@{...}` với tham số như phần trước.

### 10.2. Không pre-escape biến trước khi truyền vào template

Không nên làm:

~~~java
context.setVariable("displayName", Encode.forHtml(displayName));
~~~

rồi lại dùng:

~~~html
<span th:text="${displayName}"></span>
~~~

Vì `th:text` đã escape HTML, kết quả có thể bị double-escaped và người nhận thấy `&lt;` hoặc `&amp;`. Hãy truyền **dữ liệu gốc** vào context và để template engine escape tại đúng nơi xuất.

Chỉ khi tự ghép HTML thủ công mới gọi encoder tương ứng, và phải bảo đảm giá trị được encode một lần cho context cuối cùng.

## 11. Chọn thư viện và API phù hợp

| Công cụ/API | Công dụng | Lưu ý |
| --- | --- | --- |
| Thymeleaf `th:text` | HTML text output encoding | Dùng cho chuỗi text thông thường |
| Thymeleaf `th:href` / link expression `@{...}` | Đưa URL vào link attribute và tạo URL với tham số | Vẫn cần validation destination khi URL đến từ dữ liệu không tin cậy |
| OWASP Java Encoder `Encode.forHtml` | Encode cho HTML text context | Không dùng thay cho URL validation |
| OWASP Java Encoder `Encode.forHtmlAttribute` | Encode cho HTML attribute context | Không thay URL component encoding |
| Spring `UriComponentsBuilder` | Xây dựng URI từ path/query components | Encode từng biến đúng vị trí |
| Java `URI` | Parse và kiểm tra cấu trúc URI | Cần policy allowlist riêng |
| OWASP Java HTML Sanitizer / jsoup Safelist | Sanitize rich HTML theo allowlist | Chỉ dùng khi nghiệp vụ thật sự cần nhận HTML |
| `MimeMessageHelper` | Tạo body plain/HTML và MIME parts | Không tự inline CSS, sanitize HTML hoặc validate URL |
| `JavaMailSender` | Gửi MIME message | Không bảo đảm client render giống nhau |

Nếu cần dùng OWASP Java Encoder trực tiếp, thêm dependency tương ứng vào dự án và quản lý version qua dependency management. Không tự viết một bộ encoder mới bằng vài lệnh replace.

## 12. Những lỗi thường gặp và cách xử lý

| Lỗi | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Tên người dùng làm vỡ HTML | Nối dữ liệu trực tiếp vào HTML text | Dùng `th:text` hoặc `Encode.forHtml` |
| Dấu nháy tạo thêm attribute | Không encode giá trị trong thuộc tính HTML | Dùng `th:attr`/`th:href` phù hợp hoặc `Encode.forHtmlAttribute`; luôn quote attribute |
| Link bị thêm query parameter ngoài ý muốn | Nối chuỗi token chứa `&`/`=` | Dùng URI builder và encode query component |
| Link trỏ tới domain lạ | Chỉ URL-encode mà không kiểm tra scheme/host | Dùng allowlist; ưu tiên base URL tin cậy |
| Link có `javascript:` | HTML attribute encoding không kiểm tra scheme | Validate scheme và destination trước khi render |
| HTML hiển thị `&lt;strong&gt;` | Dữ liệu bị escape hai lần | Truyền dữ liệu gốc cho template engine; chỉ escape ở sink cuối |
| Thẻ rich text hiển thị nguyên văn | Dùng text escaping trong khi sản phẩm muốn render rich HTML | Sanitize theo allowlist rồi mới chèn bằng API unescaped phù hợp |
| Rich HTML chứa event handler/script | Tin rằng mail client sẽ tự lọc | Sanitize server-side và giới hạn thẻ/attribute/protocol |
| Plain text hiện `&amp;` | Dùng HTML encoder cho body plain text | Không HTML-escape nội dung `text/plain` |
| Tiêu đề có thể bị chèn dòng | Dùng input chưa kiểm soát trong header | Validate CR/LF, dùng `setSubject` và API mail |
| CSS bị chèn giá trị lạ | Đưa dữ liệu không tin cậy vào `style` | Dùng enum/allowlist style cố định |

### 12.1. Không dùng một hàm escape cho mọi chỗ

~~~java
String safe = Encode.forHtml(untrusted);
String html = "<a href=\"" + safe + "\">Mở</a>";
~~~

`Encode.forHtml` được thiết kế cho HTML text node. Không dùng nó như giải pháp tổng quát cho URL/attribute. Khi đặt URL vào `href`, phải tạo/validate URL trước rồi dùng **HTML attribute encoder** cho giá trị cuối.

### 12.2. Không encode toàn bộ HTML template

Nếu encode toàn bộ template sau khi đã tạo, các thẻ hợp lệ như `<p>`, `<a>` và `<table>` cũng biến thành text. Hãy encode **biến dữ liệu**, không encode cả markup tin cậy.

~~~java
String html = "<p>Xin chào "
        + Encode.forHtml(displayName)
        + "</p>";
~~~

Markup `<p>` do ứng dụng kiểm soát được giữ nguyên; chỉ dữ liệu động được encode.

## 13. Kiểm thử contextual escaping

Kiểm thử nên tập trung vào **đúng context đầu ra**, không chỉ xác nhận rằng một hàm escape đã được gọi. Có thể chuẩn bị dữ liệu mẫu:

| Input | Vị trí đầu ra | Điều cần quan sát |
| --- | --- | --- |
| `Lan <Admin> & Support` | HTML text | Ký tự đặc biệt hiển thị như văn bản; không sinh thẻ |
| `" onmouseover="...` | Quoted attribute | Không tạo attribute mới hoặc đóng dấu nháy |
| `abc&next=home` | Query parameter | Vẫn là một giá trị token; không tạo query parameter ngoài ý muốn |
| `report/2026` | Path segment | Dấu slash trong dữ liệu không tạo cấp path ngoài dự kiến |
| `javascript:...` | URL destination | Bị policy từ chối trước khi tạo link |
| `<strong>Lan</strong>` | Plain text | Hiển thị nguyên chuỗi, không HTML-escape |
| `<strong>Lan</strong>` | Rich HTML | Chỉ render nếu sanitizer policy cho phép |
| Chuỗi có CR/LF | Subject/header | Không thể tạo header phụ hoặc dòng header mới |
| Text có dấu tiếng Việt | HTML/plain body | Nội dung hiển thị đúng với charset UTF-8 |

### 13.1. Kiểm tra output HTML của template

Một bài test template có thể render với giá trị đặc biệt rồi xác nhận output:

~~~java
Context context = new Context();
context.setVariable("displayName", "<img src=x onerror=alert(1)>");
String html = templateEngine.process("mail/verification", context);

// Kiểm tra HTML render có chứa entity thay vì thẻ do input tạo ra.
assertThat(html).contains("&lt;img");
assertThat(html).doesNotContain("<img src=x");
~~~

Đây là ví dụ minh họa; import và assertion phụ thuộc test framework của dự án. Với URL, cần kiểm tra thêm URL đã được tạo đúng query/path component và scheme/host đã được allowlist chấp nhận.

### 13.2. Kiểm tra raw MIME và nội dung client hiển thị

Sau khi template render:

1. Xem HTML đã render, xác nhận biến text và attribute được escape.
2. Xem `MimeMessage` đã serialize, xác nhận body là `text/html` và charset phù hợp.
3. Kiểm tra phần `text/plain` nếu gửi alternative.
4. Gửi tới SMTP sink để xem bản email được nhận.
5. Mở trên các mail client mục tiêu để quan sát hành vi render và link.

Không log token xác minh hoặc nội dung email thật trong test output dùng chung. Dùng token giả và domain thử nghiệm để kiểm tra encoding.

## 14. Checklist theo từng context

| Context | Trước khi xuất | Encoder/biện pháp |
| --- | --- | --- |
| HTML text | Giá trị là dữ liệu text bình thường | `th:text` hoặc `Encode.forHtml` |
| HTML attribute | Attribute đã xác định và được quote | `th:attr`/`th:href` hoặc `Encode.forHtmlAttribute` |
| URL query | Xác định query parameter và giá trị | `UriComponentsBuilder`/URI component encoding |
| URL path | Xác định từng path segment | `pathSegment` hoặc encoder cho path segment |
| URL destination | Xác định scheme, host, port, redirect policy | Validation/allowlist; encoding không thay validation |
| Plain text body | Chuỗi văn bản, line ending hợp lý | Không HTML-escape; đặt qua `setText(text, false)` |
| Subject/header | Không có CR/LF hoặc header syntax tùy ý | Validate và dùng API Jakarta Mail/Spring Mail |
| Rich HTML | Xác định thẻ/attribute/protocol được phép | Sanitizer allowlist, sau đó dùng đúng HTML body context |
| CSS | Giá trị thuộc tập được phép | Enum/allowlist; tránh chuỗi CSS tùy ý |
| JavaScript | Không nhúng dữ liệu vào script/event handler | Tránh JavaScript trong email |

## 15. Ghi nhớ khi tạo email bằng Spring Framework Mail

Một quy trình an toàn có thể mô tả:

~~~text
Nguồn dữ liệu nghiệp vụ
        |
        v
Validate theo nghiệp vụ (recipient, subject, token, URL destination)
        |
        +--> Build URL: encode path/query component
        |
        v
Template engine
        |
        +--> HTML text: th:text / HTML text encoder
        |
        +--> HTML attribute: th:href / attribute encoder
        |
        +--> Rich HTML: sanitizer allowlist nếu thực sự cần
        |
        +--> Plain text: giữ văn bản, không HTML escape
        |
        v
MimeMessageHelper.setText(plainText, html)
        |
        v
JavaMailSender.send(message)
~~~

`JavaMailSender` và `MimeMessageHelper` chịu trách nhiệm tạo/vận chuyển MIME message. Chúng không tự quyết định dữ liệu nào được phép đi vào link, không tự sanitize rich HTML và không tự escape mọi chuỗi theo context. Trách nhiệm đó thuộc tầng tạo nội dung/template.

Khi đưa dữ liệu vào **HTML text**, dùng HTML text encoding; khi đặt vào **HTML attribute**, dùng attribute encoding; khi đưa dữ liệu vào **URL**, encode đúng từng component và validate destination; với **plain text**, không áp dụng HTML escaping. Nếu cho phép rich HTML, sanitize theo allowlist. Đặt các bước này đúng vị trí giúp email giữ nguyên dữ liệu nghiệp vụ, tránh phá vỡ markup và giảm nguy cơ nội dung động bị diễn giải thành cú pháp ngoài ý muốn.
