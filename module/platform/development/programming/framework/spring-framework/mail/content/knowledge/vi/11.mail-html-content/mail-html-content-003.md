# Escape dữ liệu người dùng trước khi đưa vào HTML

Email HTML giúp ứng dụng Spring trình bày thông báo với tiêu đề, đoạn văn, nút hành động và hình ảnh. Tuy nhiên, khi nội dung email có **dữ liệu do người dùng nhập** — chẳng hạn tên, ghi chú giao hàng, tên sản phẩm hoặc phản hồi hỗ trợ — lập trình viên phải bảo đảm dữ liệu đó được hiểu là **văn bản**, không phải cú pháp HTML.

Nếu nối thẳng một chuỗi không đáng tin cậy vào body HTML, các ký tự như `<`, `>`, `&` và dấu nháy có thể thay đổi cấu trúc tài liệu. Kết quả có thể là bố cục bị hỏng, liên kết không mong muốn xuất hiện hoặc nội dung do người dùng nhập bị trình bày như một thông báo chính thức. **HTML escaping** là bước chuyển những ký tự có ý nghĩa trong cú pháp HTML thành các tham chiếu ký tự để giữ chúng ở vai trò dữ liệu.

Trong **Spring Framework Mail**, `MimeMessageHelper.setText(html, true)` đặt nội dung dưới dạng HTML cho email. Nó **không tự escape, làm sạch hoặc kiểm duyệt từng phần dữ liệu được ghép vào chuỗi HTML**. Nếu dùng template engine như Thymeleaf, ứng dụng có thể để template thực hiện escaping tại vị trí xuất. Nếu tự xây chuỗi HTML, lập trình viên phải đảm nhận bước đó.

Bài này trình bày nguyên lý, những ngữ cảnh khác nhau, ví dụ Spring Boot/`JavaMailSender`, xử lý template, URL và rich text, cùng những giới hạn mà escaping không thể giải quyết.

## 1. Vì sao dữ liệu động trong email HTML có thể nguy hiểm?

Xét một mẫu thư xác nhận:

~~~html
<html>
  <body>
    <h2>Đã nhận đơn hàng</h2>
    <p>Xin chào, Nguyễn An!</p>
    <p>Đơn hàng đã được xác nhận.</p>
  </body>
</html>
~~~

Trong HTML này, các thẻ `<h2>`, `<p>` và `<strong>` do ứng dụng quản lý là **markup đáng tin cậy**. Tên “Nguyễn An” có thể lấy từ cơ sở dữ liệu, nhưng nguồn gốc cuối cùng là một biểu mẫu người dùng.

Cách dựng HTML dễ mắc lỗi:

~~~java
String name = request.customerName();

String html = "<p>Xin chào, " + name + "!</p>";
~~~

Giả sử người dùng đã nhập tên:

~~~text
An</p><p>Đơn hàng đã bị hủy</p><p>
~~~

Nếu nối nguyên văn, thông điệp có thể trở thành:

~~~html
<p>Xin chào, An</p>
<p>Đơn hàng đã bị hủy</p>
<p>!</p>
~~~

Dòng “Đơn hàng đã bị hủy” không đến từ quy trình xác nhận đơn hàng. Nó được tạo ra vì dữ liệu của một trường văn bản bị trình phân tích HTML coi là **cấu trúc**.

Một số ứng dụng đọc email chặn JavaScript và nhiều dạng HTML nguy hiểm. Tuy nhiên, **không nên lấy việc mail client có bộ lọc làm biện pháp bảo vệ chính**: cơ chế lọc khác nhau theo sản phẩm, còn việc làm sai nội dung hiển thị có thể xảy ra ngay cả khi mọi script đều bị chặn.

### Ranh giới dữ liệu và HTML

~~~mermaid
flowchart LR
    A["Tên / ghi chú / nội dung do người dùng nhập"] --> B["Dữ liệu String"]
    B --> C["Escape tại ngữ cảnh xuất HTML"]
    C --> D["Template HTML đáng tin cậy"]
    D --> E["MimeMessageHelper"]
    E --> F["JavaMailSender"]
    F --> G["SMTP relay"]
~~~

Điểm mấu chốt là bước chuyển từ **chuỗi dữ liệu** thành **nội dung một tài liệu HTML**. Dữ liệu đến từ database, API, hàng đợi hay file CSV vẫn có thể chứa ký tự đặc biệt; nguồn trung gian không làm nó tự trở thành HTML đáng tin cậy.

## 2. HTML escaping hoạt động ra sao?

Một số ký tự có ý nghĩa cú pháp trong HTML. Khi muốn chúng xuất hiện như văn bản, ta biểu diễn chúng bằng HTML entity hoặc character reference.

| Dữ liệu gốc | Biểu diễn HTML phổ biến | Ý nghĩa |
| --- | --- | --- |
| `&` | `&amp;` | Không để dấu `&` mở đầu một entity ngoài ý muốn. |
| `<` | `&lt;` | Không để dữ liệu tạo ký hiệu bắt đầu một thẻ. |
| `>` | `&gt;` | Giữ ký tự trong vai trò văn bản. |
| `"` | `&quot;` | Giữ dấu nháy kép khi chèn vào thuộc tính được bao bằng dấu nháy. |
| `'` | `&#39;` | Giữ dấu nháy đơn khi chèn vào thuộc tính được bao bằng dấu nháy. |

Ví dụ tên khách hàng:

~~~text
An <Bảo> & Co.
~~~

Được escape cho HTML text:

~~~html
An &lt;Bảo&gt; &amp; Co.
~~~

Và được đặt vào template:

~~~html
<p>Xin chào, An &lt;Bảo&gt; &amp; Co.!</p>
~~~

Khi ứng dụng đọc email hiển thị HTML, người nhận sẽ thấy:

~~~text
Xin chào, An <Bảo> & Co.!
~~~

**Escaping không làm mất nội dung gốc.** Nó chỉ thay cách biểu diễn để trình phân tích HTML không coi ký tự dữ liệu là lệnh đánh dấu.

### Unicode và escaping là hai vấn đề khác nhau

Chữ `Nguyễn`, `Đặng`, ký tự `á` và emoji được biểu diễn bằng Unicode, thường dùng **UTF-8** trong MIME. HTML escaping chủ yếu xử lý những ký tự có ý nghĩa cú pháp; không có lý do phải bỏ dấu tiếng Việt để tránh HTML injection.

Ví dụ:

~~~text
Tên gốc:  "Chào 🌷 <An> & Bình"
HTML:     "Chào 🌷 &lt;An&gt; &amp; Bình"
~~~

Tầng MIME của Jakarta Mail sẽ xử lý charset; tầng render HTML quyết định những ký tự cần được escape. **UTF-8 đúng không đồng nghĩa HTML an toàn.**

### Encoding không phải encryption

Dữ liệu `&lt;` và `&amp;` có thể được bất kỳ trình đọc HTML nào giải mã để hiển thị. Đây không phải mã hóa bí mật. Việc ứng dụng dùng STARTTLS để bảo vệ kết nối SMTP cũng không thay thế HTML escaping của body.

## 3. Escape dữ liệu, không escape toàn bộ template

Một template có cấu trúc do ứng dụng quản lý:

~~~html
<h2>Đã xác nhận đơn hàng</h2>
<p>Khách hàng: {{customerName}}</p>
<p>Ghi chú: {{customerNote}}</p>
~~~

Giả sử hai giá trị động:

~~~text
customerName = "Nguyễn <An>"
customerNote = "Gọi sau 17:00 & hỏi lễ tân"
~~~

Chỉ escape **giá trị được đưa vào các placeholder**. Kết quả:

~~~html
<h2>Đã xác nhận đơn hàng</h2>
<p>Khách hàng: Nguyễn &lt;An&gt;</p>
<p>Ghi chú: Gọi sau 17:00 &amp; hỏi lễ tân</p>
~~~

Không được thực hiện cách sau:

~~~java
String completeHtml = "<p>Xin chào, " + safeName + "</p>";

// Sai mục đích: toàn bộ thẻ <p> cũng bị biến thành text.
String visibleTags = escapeHtmlText(completeHtml);
~~~

Nếu escape toàn bộ HTML, các dấu `<` và `>` của chính template cũng biến thành `&lt;` và `&gt;`. Người nhận có thể thấy nguyên chuỗi `<p>` thay vì đoạn văn được định dạng.

Quy tắc dễ nhớ: **template quyết định cấu trúc; dữ liệu động được escape cho vị trí chèn**.

## 4. Không có một phép escape dùng được cho mọi ngữ cảnh

Đây là nguyên tắc quan trọng khi xử lý HTML email. Cùng một chuỗi người dùng nhưng nếu được đưa vào **text**, **attribute**, **URL**, **CSS** hay **JavaScript** thì cần biện pháp khác nhau.

| Ngữ cảnh | Ví dụ | Cách xử lý |
| --- | --- | --- |
| HTML text node | `<p>data</p>` | HTML-escape dữ liệu. |
| Thuộc tính đặt trong dấu nháy | `<span title="data">` | Escape ký tự có ý nghĩa cho thuộc tính, luôn dùng dấu nháy bao quanh. |
| URL attribute | `<a href="data">` | Kiểm tra scheme/host, xây URL đúng cách, rồi escape ở ngữ cảnh thuộc tính. |
| CSS | `style="color: data"` | Chỉ chọn giá trị từ allowlist; không chèn tùy ý. |
| JavaScript | `<script>data</script>` hoặc `onclick="data"` | Tránh đưa dữ liệu động; email HTML không nên phụ thuộc script. |
| Tên thẻ / tên thuộc tính | `<data>` hoặc `data="..."` | Không dùng dữ liệu người dùng làm tên cú pháp. |

### 4.1. Text node

Vị trí phổ biến nhất:

~~~html
<p>Xin chào, {{customerName}}!</p>
~~~

Nếu tên chứa `<` hoặc `&`, dữ liệu cần HTML-escape trước khi thay placeholder. Đây là trường hợp một hàm `escapeHtmlText(...)` đơn giản giải quyết tốt.

### 4.2. Thuộc tính HTML

Ví dụ:

~~~html
<span title="{{customerName}}">Xem tên</span>
~~~

Với:

~~~text
An "VIP" & Co.
~~~

nên tạo:

~~~html
<span title="An &quot;VIP&quot; &amp; Co.">Xem tên</span>
~~~

Dấu nháy kép trong giá trị được escape để không đóng sớm thuộc tính. **Không nên tạo thuộc tính không có dấu nháy bao quanh** rồi nối dữ liệu tùy ý vì ngữ cảnh đó có thêm những ký tự phân cách khác.

### 4.3. URL trong href hoặc src

Ví dụ:

~~~html
<a href="{{destination}}">Xem đơn hàng</a>
~~~

Chỉ escape dấu `"` và `<` chưa đủ. Nếu `destination` chỉ tới host giả mạo hoặc dùng scheme không được phép, link vẫn nguy hiểm về ý nghĩa. Đối với email giao dịch, nên dùng **HTTPS và host do ứng dụng kiểm soát**, xây path/query theo cú pháp URL, rồi escape giá trị cuối cùng khi đưa vào thuộc tính HTML.

### 4.4. CSS, script và event handler

Tránh những mẫu sau khi `data` là chuỗi tùy ý:

~~~html
<div style="{{data}}">Nội dung</div>
<button onclick="{{data}}">Bấm</button>
<script>var note = "{{data}}";</script>
<!-- {{data}} -->
~~~

HTML text escaping không phải bộ mã hóa đúng cho mọi cấu trúc CSS/JS/comment. Hơn nữa, nhiều trình đọc thư vô hiệu hóa JavaScript. Với email HTML, nên giữ CSS, bố cục, hành vi và các thẻ trong **template được phê duyệt**; dữ liệu người dùng chỉ xuất hiện trong các vị trí văn bản thích hợp.

## 5. Tự escape text bằng Java khi không dùng template engine

Có thể viết một hàm minh họa nguyên tắc HTML-escape. Với ứng dụng đơn giản, hàm sau chuyển những ký tự cú pháp phổ biến thành entity.

~~~java
public final class MailHtmlEscaper {

    private MailHtmlEscaper() {
    }

    public static String escapeHtmlText(String value) {
        if (value == null) {
            throw new IllegalArgumentException(
                    "Không thể escape giá trị null"
            );
        }

        StringBuilder out = new StringBuilder(
                value.length() + 16
        );

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);

            switch (c) {
                case '&'  -> out.append("&amp;");
                case '<'  -> out.append("&lt;");
                case '>'  -> out.append("&gt;");
                case '"'  -> out.append("&quot;");
                case '\'' -> out.append("&#39;");
                default   -> out.append(c);
            }
        }

        return out.toString();
    }
}
~~~

Ví dụ:

~~~java
String name = "An <Bảo> & Co.";

String html = "<p>Xin chào, "
        + MailHtmlEscaper.escapeHtmlText(name)
        + "!</p>";
~~~

Kết quả:

~~~html
<p>Xin chào, An &lt;Bảo&gt; &amp; Co.!</p>
~~~

Hàm minh họa giữ nguyên các ký tự Unicode khác. Nó **không phải bộ xử lý đầy đủ mọi ngữ cảnh**, không kiểm tra URL, không sanitize HTML người dùng, không xử lý dữ liệu đưa vào CSS/JS và không quyết định những thẻ nào được phép.

Khi có nhiều mẫu email hoặc có rich text, nên sử dụng **template engine với escaping thích hợp** hoặc thư viện HTML sanitization đáng tin cậy thay vì tự xây một hệ thống xử lý HTML hoàn chỉnh.

### HtmlUtils của Spring

Nếu ứng dụng có module `spring-web` trên classpath, có thể dùng:

~~~java
import org.springframework.web.util.HtmlUtils;

String safeName = HtmlUtils.htmlEscape(customerName);
~~~

`HtmlUtils.htmlEscape(...)` tạo chuỗi đã escape cho HTML. Tuy nhiên:

- Nó không xác thực `href`, domain hoặc URL.
- Nó không phải HTML sanitizer với chính sách thẻ/thuộc tính.
- Ứng dụng chỉ có `spring-boot-starter-mail` không nhất thiết có `HtmlUtils`, vì lớp này thuộc `spring-web`.

Không nhất thiết phải thêm cả web starter chỉ để escape một trường nếu template engine hoặc tiện ích đã có trong dự án đáp ứng yêu cầu.

## 6. Dựng HTML từ dữ liệu đã escape

Giả sử hệ thống tạo email xác nhận đã nhận một yêu cầu hỗ trợ.

Dữ liệu từ người dùng:

~~~text
customerName = "An <Bảo>"
customerNote = "Gọi trước 17:00 & nhắn nếu không gặp"
~~~

Cách dựng một template nhỏ trong Java:

~~~java
String safeName =
        MailHtmlEscaper.escapeHtmlText(customerName);

String safeNote =
        MailHtmlEscaper.escapeHtmlText(customerNote);

String html = """
        <html>
          <body>
            <h2>Đã nhận yêu cầu hỗ trợ</h2>
            <p>Xin chào, %s!</p>
            <p>Ghi chú của bạn: %s</p>
            <p>Chúng tôi sẽ phản hồi trong ứng dụng.</p>
          </body>
        </html>
        """.formatted(safeName, safeNote);
~~~

`formatted(...)` chỉ thay placeholder `%s` bằng các giá trị đã được chuẩn bị. **Nó không tự escape HTML**. Ở đây, sự an toàn của vị trí text node đến từ việc `safeName` và `safeNote` đã được escape trước khi chèn.

HTML tạo ra:

~~~html
<html>
  <body>
    <h2>Đã nhận yêu cầu hỗ trợ</h2>
    <p>Xin chào, An &lt;Bảo&gt;!</p>
    <p>Ghi chú của bạn:
       Gọi trước 17:00 &amp; nhắn nếu không gặp</p>
    <p>Chúng tôi sẽ phản hồi trong ứng dụng.</p>
  </body>
</html>
~~~

Đây là cấu trúc có ý nghĩa: phần tử `<h2>` và `<p>` là markup do lập trình viên chọn; tên và ghi chú chỉ là dữ liệu, không thể tạo thêm thẻ từ những dấu `<` đã được escape.

## 7. Spring Framework Mail: send HTML không có nghĩa là sanitize HTML

Để gửi HTML qua Spring Mail, ứng dụng thường tạo `MimeMessage` và sử dụng `MimeMessageHelper`:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SupportReceiptMailService {

    private final JavaMailSender mailSender;

    public SupportReceiptMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReceipt(
            String recipient,
            String customerName,
            String customerNote) throws MessagingException {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Cần địa chỉ người nhận"
            );
        }

        String name = requireText(customerName, "Tên");
        String note = requireText(customerNote, "Ghi chú");

        // Plain text: dùng dữ liệu logic, không HTML-escape.
        String plainText = """
                Xin chào, %s!

                Hệ thống đã nhận ghi chú:
                %s

                Chúng tôi sẽ phản hồi trong ứng dụng.
                """.formatted(name, note);

        // HTML: escape từng biến đặt ở text node.
        String safeName =
                MailHtmlEscaper.escapeHtmlText(name);
        String safeNote =
                MailHtmlEscaper.escapeHtmlText(note);

        String htmlText = """
                <html>
                  <body>
                    <h2>Đã nhận yêu cầu hỗ trợ</h2>
                    <p>Xin chào, %s!</p>
                    <p>Ghi chú: %s</p>
                    <p>Chúng tôi sẽ phản hồi trong ứng dụng.</p>
                  </body>
                </html>
                """.formatted(safeName, safeNote);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("support@example.org");
        helper.setTo(recipient);
        helper.setSubject("Hệ thống đã nhận yêu cầu của bạn");
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }

    private static String requireText(
            String value,
            String fieldName) {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " không được để trống"
            );
        }

        return value;
    }
}
~~~

Ví dụ giả định class `MailHtmlEscaper` đã được tạo theo phần trước. Cần cấu hình SMTP, tài khoản và địa chỉ From được nhà cung cấp cho phép. Trong ứng dụng thực, còn phải xác thực địa chỉ nhận, giới hạn độ dài ghi chú và kiểm soát người được phép nhận email. Đó là các quy tắc độc lập với HTML escaping.

### Vì sao plain text không cần HTML escaping?

Cùng một tên `An <Bảo>`:

| Nơi sử dụng | Biểu diễn |
| --- | --- |
| Dữ liệu gốc trong Java | `An <Bảo>` |
| Body `text/plain` | `An <Bảo>` |
| Chuỗi đưa vào HTML text node | `An &lt;Bảo&gt;` |
| Nội dung người đọc thấy trong HTML | `An <Bảo>` |

Trong một MIME part `text/plain`, các ký tự `<` và `>` không mang chức năng đánh dấu HTML. Nếu đưa chuỗi đã escape vào phần plain text, người nhận có thể thấy `&lt;Bảo&gt;` thay vì `<Bảo>`.

### setText(plainText, htmlText) tạo gì?

Với helper ở chế độ multipart, `setText(plainText, htmlText)` tạo hai cách biểu diễn cùng một nội dung:

~~~text
multipart/alternative
├── text/plain
└── text/html
~~~

Tùy cấu trúc MIME thực, `multipart/alternative` có thể nằm trong một container ngoài như `multipart/mixed` hoặc `multipart/related`. Mỗi bản cần mang cùng nội dung chính. Bản plain dùng dữ liệu logic; bản HTML dùng markup của template và escaping theo ngữ cảnh.

**Không có bước nào ở `MimeMessageHelper` tự phân loại chuỗi HTML nào “đáng tin cậy”.** Phương thức chỉ đặt nội dung, mime type và cấu trúc part.

## 8. Cấu hình Spring Boot cho ví dụ gửi HTML

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Một cấu hình SMTP submission minh họa:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

Hostname dùng để minh họa, không đại diện một dịch vụ SMTP cụ thể. Bí mật cần được lấy từ môi trường triển khai hoặc kho secret và tránh ghi vào Git.

Cấu hình trên kiểm soát **kết nối gửi thư**; nó không thay cho bước escape dữ liệu trong HTML. Tương tự, việc gửi qua TLS đúng cách không làm một chuỗi HTML có dữ liệu không đáng tin cậy tự an toàn.

## 9. Thymeleaf: escape tại điểm render template

Nếu một hệ thống có nhiều mẫu email HTML, tự nối chuỗi Java trở nên khó bảo trì. **Thymeleaf** là một template engine thường dùng trong ứng dụng Spring Boot; nó cung cấp cách xuất biến vào text node với escaping phù hợp.

### 9.1. Phụ thuộc

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

`spring-boot-starter-thymeleaf` phụ trách rendering, còn `spring-boot-starter-mail` phụ trách tích hợp gửi email. Hai chức năng không thay thế nhau.

### 9.2. Template HTML

Tạo một file trong classpath:

~~~text
src/main/resources/templates/mail/support-receipt.html
~~~

Nội dung:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
  <head>
    <meta charset="UTF-8">
    <title>Đã nhận yêu cầu hỗ trợ</title>
  </head>
  <body>
    <h2>Đã nhận yêu cầu hỗ trợ</h2>

    <p>
      Xin chào,
      <strong th:text="${customerName}">Tên khách hàng</strong>!
    </p>

    <p>Ghi chú của bạn:</p>
    <p th:text="${customerNote}">Ghi chú mặc định</p>

    <p>Chúng tôi sẽ phản hồi trong ứng dụng.</p>
  </body>
</html>
~~~

`th:text` đặt biến vào **nội dung văn bản của phần tử** và thực hiện escaping thích hợp. Nếu `customerName` là `An <Bảo>`, dữ liệu được biểu diễn để người nhận nhìn thấy chữ `An <Bảo>`, không tạo thẻ mới.

Để giữ nội dung chữ tiếng Việt, chỉ cần dữ liệu Unicode đúng và charset thích hợp. Không cần dùng unescaped output.

### 9.3. Render và gửi

~~~java
import java.util.Locale;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class TemplateSupportMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;

    public TemplateSupportMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine) {

        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
    }

    public void send(
            String recipient,
            String customerName,
            String customerNote) throws MessagingException {

        Context context =
                new Context(Locale.forLanguageTag("vi-VN"));

        // Truyền dữ liệu logic chưa HTML-escape vào template.
        context.setVariable("customerName", customerName);
        context.setVariable("customerNote", customerNote);

        String html = templateEngine.process(
                "mail/support-receipt",
                context
        );

        String plainText = """
                Xin chào, %s!

                Hệ thống đã nhận ghi chú:
                %s
                """.formatted(customerName, customerNote);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("support@example.org");
        helper.setTo(recipient);
        helper.setSubject("Hệ thống đã nhận yêu cầu");
        helper.setText(plainText, html);

        mailSender.send(message);
    }
}
~~~

Ví dụ này tập trung vào phần rendering HTML; trong hệ thống thật cần thêm kiểm tra giá trị `null`, độ dài, quyền nhận và cấu hình gửi thư phù hợp.

**Tại sao truyền dữ liệu gốc vào template?** Vì `th:text` đã là nơi đảm nhiệm escaping. Nếu backend tự thay `&` thành `&amp;` trước khi truyền vào biến, template có thể lại escape dấu `&` lần nữa và tạo dữ liệu bị double escaping.

## 10. Phân biệt th:text và th:utext

Hai cú pháp có ý nghĩa khác nhau:

~~~html
<!-- Dùng cho văn bản không đáng tin cậy -->
<p th:text="${customerNote}">Ghi chú</p>

<!-- Xuất nội dung như HTML không escape -->
<p th:utext="${customerNote}">Ghi chú</p>
~~~

- **`th:text`**: xuất dữ liệu như text, có escaping theo ngữ cảnh template.
- **`th:utext`**: xuất *unescaped text*, có thể được diễn giải thành markup HTML.

Nếu `customerNote` chứa `<strong>Ưu tiên</strong>`, `th:text` hiển thị đúng chuỗi người dùng nhập theo dạng văn bản. `th:utext` có thể làm chữ “Ưu tiên” trở thành một phần tử HTML đậm.

Cách unescaped **không phải lựa chọn phù hợp cho tên khách hàng, ghi chú, bình luận hoặc trường văn bản tự do**.

Trong Thymeleaf HTML inlining, cú pháp escaped như `[[...]]` và unescaped như `[(...)]` cũng cần được phân biệt. Đừng đổi sang unescaped output chỉ vì thấy một ký tự đặc biệt trong dữ liệu; nếu cần hiển thị chữ nguyên bản, escaped output vẫn làm việc đó.

### Khi nào mới có thể dùng unescaped HTML?

Đôi khi ứng dụng thật sự muốn cho phép người dùng soạn **rich text**: đoạn in đậm, danh sách, liên kết hoặc định dạng giới hạn. Khi đó, escape toàn bộ dữ liệu sẽ làm thẻ trở thành chữ, không còn định dạng.

Giải pháp không phải đưa HTML tùy ý thẳng vào `th:utext`. Cần **HTML sanitization theo allowlist** trước khi render: chỉ chấp nhận những thẻ, thuộc tính và URL đã được phê duyệt, loại bỏ cấu trúc không mong muốn và bảo đảm đầu ra dùng đúng ngữ cảnh.

Đây là hai bài toán khác nhau:

| Trường hợp | Phương pháp |
| --- | --- |
| Tên hoặc ghi chú phải hiện như văn bản | HTML escaping, ví dụ `th:text` |
| HTML do ứng dụng tạo và kiểm soát | Giữ markup trong template |
| Rich HTML từ nguồn ngoài, cần giữ một số thẻ | Sanitizer đáng tin cậy với chính sách allowlist |
| HTML bất kỳ được người dùng cung cấp | Không đưa thẳng vào email như unescaped output |

**Không nên tự viết regex chỉ xóa `<script>`** để làm sanitizer. HTML có nhiều loại thẻ, thuộc tính, cách mã hóa ký tự và tình huống parser khác nhau; cần một bộ phân tích và chính sách được duy trì phù hợp.

## 11. Escape chưa đủ khi dữ liệu nằm trong URL

Một email thường có nút “Xem chi tiết”:

~~~html
<a href="https://app.example.org/orders/A102">
  Xem đơn hàng
</a>
~~~

Ở đây có hai ngữ cảnh:

1. **Text hiển thị của link** có thể được escape như HTML text.
2. **Đích của link trong `href`** là URL; phải đúng scheme, host và cách mã hóa tham số, rồi mới được escape để nằm trong thuộc tính HTML.

Nếu người dùng cung cấp một URL bắt đầu bằng scheme không mong muốn hoặc host giả mạo, HTML escaping các dấu `<`/`"` không làm nó an toàn. **Escape theo cú pháp không thay thế xác thực ý nghĩa của URL.**

### Tạo URL từ base tin cậy

Với một email giao dịch, nên để ứng dụng kiểm soát base URL. Ví dụ mã đơn hàng dùng làm query parameter:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String codeParam = URLEncoder.encode(
        orderCode,
        StandardCharsets.UTF_8
);

// Host do ứng dụng quản lý; không lấy thẳng từ input.
String orderUrl = "https://app.example.org/orders?code="
        + codeParam;

// Escape một lần nữa khi đưa URL vào thuộc tính HTML.
String href = MailHtmlEscaper.escapeHtmlText(orderUrl);

String html = "<a href=\"" + href
        + "\">Xem đơn hàng</a>";
~~~

`URLEncoder` trong ví dụ dành cho **giá trị query parameter**, không phải cách mã hóa toàn bộ URL hoặc mọi path segment. Nếu URL gồm nhiều thành phần phức tạp, nên sử dụng một URI builder phù hợp.

Trong Thymeleaf, có thể đưa URL đã được tạo và xác thực vào template:

~~~html
<a th:href="${orderUrl}">Xem đơn hàng</a>
~~~

Template xử lý biểu diễn thuộc tính, nhưng **không thay quyết định URL nào được phép dùng**. Ứng dụng vẫn cần kiểm soát scheme HTTPS, host, đường dẫn và quyền truy cập theo yêu cầu.

### Quy tắc dành cho URL do bên ngoài đưa vào

Nếu buộc phải dùng URL từ bên ngoài, cần có chính sách kiểm tra: scheme được phép, hostname và domain được phép, cổng bất thường, ký tự điều khiển, redirect, liên kết chứa token nhạy cảm và các dạng URL gây hiểu nhầm. Với email có nút hành động chính thức, **xây link từ domain do chính ứng dụng sở hữu** thường dễ quản lý hơn.

## 12. Cách giữ xuống dòng từ ghi chú người dùng

Một trường ghi chú có thể chứa:

~~~text
Giao ở sảnh A
Gọi trước khi đến
Nếu không có người, nhắn lại
~~~

Trong HTML, newline trong chuỗi văn bản thường không tạo ba dòng giống plain text. Nếu muốn giữ xuống dòng, có thể tạo thẻ `<br>` **sau khi escape dữ liệu**:

~~~java
String note = """
        Giao ở sảnh A
        Gọi trước khi đến
        """;

String escaped = MailHtmlEscaper.escapeHtmlText(note);

String htmlFragment = escaped
        .replace("\r\n", "\n")
        .replace('\r', '\n')
        .replace("\n", "<br>");

String html = "<p>" + htmlFragment + "</p>";
~~~

Thứ tự:

1. Escape toàn bộ dữ liệu đầu vào như text.
2. Chuẩn hóa các kiểu newline.
3. Thay newline bằng `<br>` do **ứng dụng** tạo.
4. Chèn kết quả vào template tin cậy.

Nếu thay newline thành `<br>` rồi mới escape toàn bộ, thẻ xuống dòng bị biến thành chữ. Nếu cho người dùng tự nhập `<br>` rồi coi đó là markup tin cậy, ứng dụng vô tình mở đường cho những thẻ khác không được phép.

Một số client hỗ trợ CSS như `white-space: pre-line`, nhưng mức hỗ trợ CSS trong email không đồng nhất. Với nội dung quan trọng, dùng các đoạn hoặc thẻ ngắt dòng do server dựng có thể dễ dự đoán hơn.

## 13. Escape tại lúc nhập hay lúc xuất?

Giả sử khách hàng nhập:

~~~text
Mua áo "A & B"
~~~

Nếu lưu thẳng dữ liệu sau HTML escaping vào database:

~~~text
Mua áo &quot;A &amp; B&quot;
~~~

thì dữ liệu đã bị buộc vào một **định dạng hiển thị HTML**. Khi xuất sang plain text, JSON, CSV hoặc log, các entity này có thể trở thành phần văn bản không mong muốn. Nếu template engine tiếp tục escape, nội dung có thể bị double escaping.

Một quy trình dễ duy trì hơn:

1. **Tiếp nhận và kiểm tra dữ liệu gốc** theo nhu cầu nghiệp vụ.
2. **Lưu chuỗi Unicode logic**, không tự đổi thành HTML entity khi chưa biết nơi sử dụng.
3. **Khi render HTML**, escape cho đúng vị trí xuất.
4. **Khi tạo bản plain text**, sử dụng văn bản logic.
5. **Khi xuất JSON/CSV hoặc ngữ cảnh khác**, dùng quy tắc riêng của định dạng đó.

~~~mermaid
flowchart TD
    A["Chuỗi Unicode gốc"] --> B["Lớp dữ liệu / nghiệp vụ"]
    B --> C["Text/plain: giữ nội dung chữ"]
    B --> D["HTML email: escape tại render"]
    B --> E["JSON: serialize JSON"]
    B --> F["CSV: quy tắc CSV"]
~~~

Đây là nguyên tắc **output encoding theo ngữ cảnh**. Nó giúp cùng một giá trị được biểu diễn đúng ở nhiều kênh.

### Double escaping là gì?

Bắt đầu với:

~~~text
An & Bình
~~~

Escape lần một:

~~~html
An &amp; Bình
~~~

Escape lần hai:

~~~html
An &amp;amp; Bình
~~~

Khi đọc HTML, chuỗi sau có thể hiển thị thành `An &amp; Bình` chứ không phải `An & Bình`.

Vì vậy, hãy thống nhất **một nơi chịu trách nhiệm escaping**: tự escape biến trước khi chèn, **hoặc** truyền dữ liệu gốc cho một template engine có escaped output. Không thực hiện cả hai mà không hiểu rõ cấu trúc dữ liệu đang truyền.

## 14. HTML escaping không thay thế các lớp bảo vệ khác

### 14.1. Quyền truy cập và đúng người nhận

Một email được escape đúng vẫn có thể gây lộ dữ liệu nếu gửi hóa đơn của người A cho người B. Ứng dụng phải bảo đảm dữ liệu của email thuộc đúng đối tượng và địa chỉ nhận được phép.

### 14.2. Kiểm soát Subject và header

`Subject` là header MIME, không phải HTML text node. Nó nên được đặt qua:

~~~java
helper.setSubject("Đã nhận yêu cầu của bạn");
~~~

Nếu Subject chứa dữ liệu động, cần giới hạn độ dài, kiểm tra ký tự điều khiển và tránh tự ghép header thô với `\r\n`. Không nên lấy HTML escaping làm phương thức mã hóa header; Jakarta Mail có cơ chế biểu diễn Unicode trong header riêng.

### 14.3. Nội dung giàu định dạng và tài nguyên ngoài

HTML có ảnh nội tuyến `cid:`, ảnh từ xa, CSS và liên kết. Những thành phần này cần chính sách riêng về nguồn tài nguyên và quyền riêng tư. Ví dụ một `src` do người dùng tùy ý nhập có thể tải tài nguyên từ máy chủ không mong muốn; HTML escaping không kiểm soát được đích kết nối.

### 14.4. Bộ lọc HTML của mail client

Những trình đọc email có thể loại script, event handler hoặc CSS nhất định. Nhưng không nên dùng việc đó làm cơ sở tin rằng nội dung HTML do người dùng cung cấp là an toàn. Chức năng lọc của client không thay thế **server-side output escaping hoặc sanitization**.

### 14.5. Log và nội dung nhạy cảm

HTML entity không che giấu dữ liệu cá nhân. Không ghi toàn bộ raw MIME, link bí mật, thông tin người nhận hoặc tệp đính kèm vào log production chỉ để gỡ lỗi template. Nên log mã yêu cầu gửi, bước lỗi và metadata tối thiểu cần thiết.

## 15. Các lỗi thường gặp

### Lỗi 1 — Nối tên người dùng thẳng vào HTML

~~~java
String html = "<p>Chào " + name + "</p>";
helper.setText(html, true);
~~~

Cần escape `name` cho vị trí text node hoặc dùng template với escaped output. `setText(html, true)` không tự nhận biết `name` là dữ liệu người dùng.

### Lỗi 2 — Escape toàn bộ chuỗi HTML

~~~java
String html = "<p>Chào " + safeName + "</p>";
String wrong = MailHtmlEscaper.escapeHtmlText(html);
~~~

Kết quả có thể hiển thị thẻ `<p>` như chữ. Chỉ escape dữ liệu động, không escape markup do ứng dụng tạo.

### Lỗi 3 — Dùng th:utext cho ghi chú tự do

`th:utext` có mục đích xuất HTML không escape. Thay bằng `th:text` cho dữ liệu text, hoặc sanitize thật sự nếu ứng dụng cho phép rich HTML.

### Lỗi 4 — Dùng HTML escaping cho body plain text

Nếu body là `text/plain`, dữ liệu `<An>` có thể hiển thị nguyên bản. Chuyển thành `&lt;An&gt;` rồi đưa vào plain text khiến người đọc thấy entity thay vì ký tự gốc.

### Lỗi 5 — Escape dữ liệu hai lần

Backend gọi `HtmlUtils.htmlEscape(name)` rồi template lại dùng `th:text`. Chọn một cơ chế escaping tại điểm xuất, tránh `&amp;amp;`.

### Lỗi 6 — HTML-escape URL rồi xem như an toàn

Một chuỗi URL có thể không chứa ký tự cú pháp HTML mà vẫn mang scheme hoặc host không được phép. Phải kiểm soát URL trước khi escape nó vào thuộc tính.

### Lỗi 7 — Tự lọc HTML bằng regex

Việc xóa `<script>` không bảo đảm xử lý mọi HTML không an toàn. Với dữ liệu rich HTML, sử dụng sanitizer có parser và chính sách allowlist thay vì tự ghép các regex.

### Lỗi 8 — Chèn dữ liệu tùy ý vào style, onclick hoặc script

Đây không phải HTML text node. Tốt hơn là giữ CSS/markup cố định trong template, không để dữ liệu người dùng quyết định nội dung điều khiển.

### Lỗi 9 — Xóa mọi ký tự < và >

Việc xóa ký tự có thể làm hỏng tên `An <Bảo>` hoặc văn bản `5 < 10`. Escaping giữ được giá trị gốc khi hiển thị thay vì loại bỏ thông tin.

### Lỗi 10 — Tin rằng STARTTLS xử lý vấn đề HTML

TLS bảo vệ kết nối SMTP đã thương lượng, không thay đổi ý nghĩa các thẻ trong email. Đây là hai lớp trách nhiệm độc lập.

## 16. Tình huống thực hành

**Tình huống A.** Người dùng nhập tên `An <Bảo> & Co.`. Đưa vào đoạn HTML:

~~~html
<p>Xin chào, {{name}}</p>
~~~

Kết quả nên là:

~~~html
<p>Xin chào, An &lt;Bảo&gt; &amp; Co.</p>
~~~

Người nhận nhìn thấy đúng `An <Bảo> & Co.`.

**Tình huống B.** Ghi chú chứa `Giao trước 17:00 & gọi lễ tân`. Dấu `&` cần được biểu diễn ra sao trong text node?

~~~html
<p>Giao trước 17:00 &amp; gọi lễ tân</p>
~~~

**Tình huống C.** Một trường tên có dấu nháy kép: `An "VIP"`. Nếu đưa vào thuộc tính `title` với dấu nháy kép, cần escape nháy để không làm kết thúc sớm thuộc tính:

~~~html
<span title="An &quot;VIP&quot;">Xem tên</span>
~~~

**Tình huống D.** Một ghi chú có nội dung `<strong>Ưu tiên</strong>`. Nếu nghiệp vụ định nghĩa ghi chú là **text**, trình đọc nên hiển thị cả các dấu thẻ như chữ, không tự làm chữ đậm.

~~~html
<p>&lt;strong&gt;Ưu tiên&lt;/strong&gt;</p>
~~~

Nếu nghiệp vụ cho phép rich text, phải áp dụng quy trình sanitization riêng.

**Tình huống E.** Backend đã escape `An & Bình` thành `An &amp; Bình` và truyền vào template dùng `th:text`. Vì sao người nhận có thể thấy `An &amp; Bình`?

Vì dữ liệu có thể bị **double escaping**. Hãy truyền dữ liệu logic gốc cho template và để `th:text` phụ trách escaping.

**Tình huống F.** Muốn giữ ba dòng ghi chú trong HTML. Có thể cho người dùng tự gõ `<br>` không?

Không nên coi chuỗi thẻ do người dùng gõ là markup tin cậy. Hãy escape dữ liệu trước, rồi chuyển newline thành thẻ ngắt dòng do ứng dụng tạo.

**Tình huống G.** Một đường dẫn do người dùng gửi không chứa `<` hoặc `"`. Có chắc nó được phép đưa vào `href` sau HTML escaping?

Không. HTML escaping không kiểm tra scheme, host hay quyền truy cập. Cần chính sách URL và xử lý theo cấu trúc URL trước.

**Tình huống H.** Body email dùng:

~~~java
helper.setText(customerNote, false);
~~~

Có cần thay `<` thành `&lt;` trước khi gửi không?

Không cần cho việc hiển thị trong `text/plain`. Điều quan trọng là giữ nguyên văn bản logic và kiểm tra dữ liệu theo quy tắc nghiệp vụ. HTML escaping thuộc về ngữ cảnh body HTML, không phải mọi chuỗi email.

## 17. Mô hình ghi nhớ

Hãy coi một email HTML là sự kết hợp giữa **template có cấu trúc** và **dữ liệu động**:

~~~mermaid
flowchart TD
    A["Dữ liệu người dùng"] --> B["Kiểm tra nghiệp vụ / quyền truy cập"]
    B --> C{"Đưa dữ liệu vào đâu?"}
    C -->|"HTML text"| D["Escape HTML hoặc th:text"]
    C -->|"HTML attribute"| E["Escape thuộc tính, dùng dấu nháy"]
    C -->|"URL attribute"| F["Kiểm soát URL rồi escape thuộc tính"]
    C -->|"Plain text"| G["Giữ chuỗi logic"]
    C -->|"Rich HTML được phép"| H["Sanitize theo allowlist"]
    D --> I["HTML template đáng tin cậy"]
    E --> I
    F --> I
    H --> I
    I --> J["MimeMessageHelper.setText(html, true)"]
    G --> K["MimeMessageHelper: text/plain"]
    J --> L["JavaMailSender.send"]
    K --> L
~~~

Bảy điều cần ghi nhớ:

1. **`MimeMessageHelper.setText(html, true)` không tự escape dữ liệu.**
2. **Escape tại vị trí xuất HTML**, không escape toàn bộ template hoặc tự lưu mọi dữ liệu trong database dưới dạng HTML entity.
3. **Text node, thuộc tính, URL, CSS và JavaScript là các ngữ cảnh khác nhau**; một hàm escape text không xử lý tất cả.
4. **Dùng escaped output của template engine**, chẳng hạn Thymeleaf `th:text`, khi đưa chuỗi không đáng tin cậy vào văn bản HTML.
5. **Dùng HTML sanitizer allowlist** nếu cần giữ một số markup từ rich-text input; không dùng unescaped output tùy ý.
6. **Bản plain text dùng dữ liệu logic**, không dùng entity chỉ dành cho HTML.
7. **Escaping không thay thế xác thực, phân quyền, TLS, kiểm soát URL hoặc bảo vệ bí mật.**

Trong Spring Framework Mail, ứng dụng chịu trách nhiệm chuẩn bị nội dung HTML **đúng ngữ cảnh**; `MimeMessageHelper` và Jakarta Mail chịu trách nhiệm biểu diễn thành MIME, còn `JavaMailSender` thực hiện gửi qua SMTP đã cấu hình. Khi tách rõ những trách nhiệm này, tên, ghi chú và văn bản người dùng vẫn hiển thị đúng ý định mà không vô tình trở thành cấu trúc hoặc hành vi của email HTML.
