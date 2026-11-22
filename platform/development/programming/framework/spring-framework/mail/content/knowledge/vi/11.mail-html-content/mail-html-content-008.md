# Mã hóa ký tự trong subject và body

## 1. Vấn đề: email gửi được nhưng chữ tiếng Việt bị lỗi

Trong **Spring Framework Mail**, ứng dụng thường sử dụng **JavaMailSender** và **MimeMessageHelper** để gửi email tiếng Việt, HTML, ký tự đặc biệt và emoji. Một email có thể được SMTP server chấp nhận nhưng khi mở trong email client lại xuất hiện những lỗi như:

- Tiêu đề dự kiến **“Xác nhận đơn hàng”** trở thành chuỗi ký tự khó đọc hoặc các dấu hỏi.
- Subject hiển thị đúng nhưng body lại thành **“ChÃ o”** hay các ký tự thay thế.
- Body HTML hiển thị tiếng Việt đúng, nhưng phần text/plain lại bị sai dấu.
- Email trong giao diện xem trước của ứng dụng đúng, nhưng bản nhận ở Outlook hoặc Gmail lại khác.
- Tên người gửi hay tên attachment bị lỗi dù subject và nội dung thư vẫn đúng.

Đây không nhất thiết là lỗi SMTP. Email có **quy tắc mã hóa khác nhau cho header và body**; với HTML, còn phải phân biệt **HTML escaping** với **character encoding**. Muốn gửi chính xác, cần hiểu từng lớp.

Mục tiêu bài học là xây dựng email có Subject, text và HTML chứa Unicode đúng trong Spring Mail; hiểu cấu trúc MIME trên đường truyền; kiểm tra và xử lý sai charset một cách có hệ thống.

## 2. Ba lớp biến đổi ký tự cần phân biệt

Một chuỗi trong Java:

~~~java
String subject = "Xác nhận đơn hàng số 123";
String html = "<p>Xin chào, cảm ơn bạn! ✅</p>";
~~~

được biểu diễn dưới dạng **Java String**, gồm các đơn vị mã UTF-16 trong bộ nhớ. Khi xây dựng email, Jakarta Mail cần chuyển các ký tự thành byte và cấu trúc MIME. Email client giải mã cấu trúc này để hiển thị lại ký tự.

~~~text
Java String Unicode
  |
  +-- Subject / display name (header)
  |      |
  |      +--> MIME header encoding
  |             (thường dùng RFC 2047 encoded-word)
  |
  +-- text/plain / text/html (body)
         |
         +--> Character encoding: UTF-8
         |
         +--> Content-Transfer-Encoding:
                quoted-printable hoặc Base64 hoặc cơ chế khác
~~~

Nếu nội dung là HTML, dữ liệu người dùng còn đi qua bước **HTML escaping** trước khi chèn vào template:

~~~text
User input -> escape HTML -> Java String chứa HTML
    -> encode UTF-8 -> MIME transfer encoding
    -> email client decode -> render HTML
~~~

| Khái niệm | Giải quyết điều gì? | Ví dụ |
|---|---|---|
| **Character encoding / charset** | Ánh xạ ký tự Unicode thành byte và ngược lại | UTF-8 |
| **MIME header encoding** | Biểu diễn Unicode trong email header theo cách tương thích | Encoded-word dạng =?UTF-8?B?...?= |
| **Content-Transfer-Encoding** | Biểu diễn byte của body để vận chuyển an toàn qua email | quoted-printable, base64 |
| **HTML escaping** | Giúp văn bản người dùng không bị hiểu thành cú pháp HTML | Dấu < thành &lt;, & thành &amp; |

**UTF-8 không phải Base64. Base64 không phải mã hóa bảo mật. HTML escaping không thay thế UTF-8.** Các cơ chế giải quyết những lớp khác nhau của thông điệp.

## 3. Subject là header, không phải HTML body

**Subject** thuộc **header** của email. Với MIME theo kiểu truyền thống, khi subject có Unicode, thư viện thường biểu diễn bằng **encoded-word** theo RFC 2047. Cú pháp tổng quát:

~~~text
=?charset?encoding?encoded-text?=
~~~

Trong đó:

- **charset**: cách biến ký tự thành byte, thường là UTF-8.
- **encoding**: thường là B (Base64) hoặc Q (cơ chế mã hóa tương tự quoted-printable dành cho header).
- **encoded-text**: nội dung đã chuyển theo encoding.

Ví dụ từ **Café** có thể xuất hiện trên đường truyền là:

~~~text
Subject: =?UTF-8?B?Q2Fmw6k=?=
~~~

hoặc:

~~~text
Subject: =?UTF-8?Q?Caf=C3=A9?=
~~~

Cả hai cách đều biểu diễn chữ **Café**, client giải mã header rồi hiển thị cho người dùng. Subject dài có thể được chia thành nhiều encoded-word và gấp dòng header theo quy tắc MIME. Nhìn raw header thấy nhiều đoạn =?UTF-8?...?= **không đồng nghĩa có lỗi**.

### B và Q khác nhau thế nào?

| Cơ chế | Cách biểu diễn | Đặc điểm |
|---|---|---|
| **B** | Byte theo charset được mã hóa Base64 | Phù hợp tiêu đề có nhiều ký tự ngoài ASCII |
| **Q** | Một số byte được biểu diễn bằng =HH, dấu cách có thể là _ | Có thể dễ đọc trong raw header chủ yếu ASCII |

**Q-encoding trong RFC 2047 không hoàn toàn giống body quoted-printable**. Trong encoded-word kiểu Q, dấu gạch dưới có thể mang nghĩa dấu cách; các quy tắc áp dụng cho header khác với body. Không tự lấy HTML escaping hoặc quoted-printable body để mã hóa Subject.

### Cách làm với Spring Mail

**Truyền Java String Unicode bình thường vào MimeMessageHelper.setSubject(...)** và cung cấp charset UTF-8. Jakarta Mail có trách nhiệm serialize header thích hợp.

~~~java
helper.setSubject("Xác nhận đơn hàng – cảm ơn bạn ✅");
~~~

Không cần tự chuyển Subject sang Base64, không tự ghép =?UTF-8?B?...?= và **không tự encode Subject bằng một helper rồi tiếp tục truyền qua API có thể encode lần nữa**. Mã hóa hai lần có thể khiến người nhận nhìn thấy chính chuỗi encoded-word, thay vì tiêu đề.

## 4. Body dùng charset và Content-Transfer-Encoding

Body không dùng encoded-word của header cho toàn bộ nội dung. Mỗi MIME body part có thể khai báo:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

**Content-Type** cung cấp media type và charset. **Content-Transfer-Encoding** mô tả cách byte của body được biểu diễn cho transport. Email client giải mã transfer encoding **trước**, rồi dùng charset để tạo Unicode.

~~~mermaid
flowchart LR
    A[Java String] --> B[UTF-8 bytes]
    B --> C[Quoted-printable hoặc Base64]
    C --> D[MIME text/html part]
    D --> E[Decode transfer encoding]
    E --> F[Decode UTF-8]
    F --> G[Render HTML]
~~~

Ví dụ phần body sử dụng quoted-printable:

~~~mime
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<html><body><p>Xin ch=C3=A0o, Caf=C3=A9!</p></body></html>
~~~

Hai byte UTF-8 C3 A0 được thể hiện bằng =C3=A0, tương ứng ký tự **à**. C3 A9 thể hiện **é**. Email client cần giải mã cả transfer encoding lẫn charset mới hiển thị **“Xin chào, Café!”**.

Thư viện có thể chọn **Base64** thay vì quoted-printable. Không nên đặt giả định mọi body UTF-8 bắt buộc dùng quoted-printable; điều quan trọng là **MIME có khai báo đúng và dữ liệu giải mã lại chính xác**.

### Charset không khớp với byte thì sao?

Nếu byte thực là UTF-8 nhưng MIME khai báo charset ISO-8859-1, người nhận có thể thấy **“ChÃ o”**. Nếu dữ liệu bị thay bằng dấu ? từ trước khi đưa vào mail layer, chỉ sửa header MIME ở cuối pipeline không thể khôi phục nguyên bản.

**Charset phải mô tả cách byte thực sự được tạo**, không chỉ là một nhãn mong muốn.

## 5. HTML meta charset không thay thế MIME charset

Một template HTML có thể chứa:

~~~html
<!doctype html>
<html lang="vi">
  <head><meta charset="UTF-8"></head>
  <body><p>Chào bạn, cảm ơn đã đăng ký!</p></body>
</html>
~~~

Trên trang web, meta charset giúp trình duyệt hiểu encoding của nguồn. Nhưng **trong email MIME, body part đã có Content-Type và charset**. Email client có thể xử lý meta khác nhau; chỉ thêm meta vào HTML body trong khi truyền byte theo charset sai **không phải cách sửa đáng tin cậy**.

Nên đảm bảo đồng nhất:

1. Java String chứa đúng Unicode.
2. MimeMessageHelper dùng UTF-8 để dựng part.
3. MIME khai báo text/html; charset=UTF-8 hoặc giá trị tương đương.
4. Transfer encoding được thư viện tạo phù hợp với body.
5. Nếu có meta charset trong HTML, nó không mâu thuẫn với MIME charset.

## 6. Cấu hình UTF-8 trong Spring Boot

Spring Boot có thuộc tính **spring.mail.default-encoding** để cấu hình charset mặc định cho JavaMailSender do Boot tự cấu hình:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    default-encoding: UTF-8
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Host và cổng ở đây chỉ minh họa; credential phải lấy từ môi trường triển khai hoặc secret manager. Timeout tính bằng mili giây. Việc SMTP submission có TLS/AUTH giúp bảo vệ đường gửi và chứng minh danh tính client, nhưng **không tự thay charset** của nội dung.

Nếu tạo sender thủ công:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.example.net");
sender.setPort(587);
sender.setDefaultEncoding(StandardCharsets.UTF_8.name());
~~~

Trong những đoạn code quan trọng, có thể truyền **UTF-8 tường minh vào MimeMessageHelper** để tránh phụ thuộc vào default encoding của sender khác. Một cấu hình email UTF-8 không tự sửa dữ liệu đã sai ở HTTP request, database hoặc template engine trước đó.

## 7. Gửi Subject và HTML body tiếng Việt bằng MimeMessageHelper

Ví dụ Spring service:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class VietnameseHtmlMailService {
    private final JavaMailSender mailSender;

    public VietnameseHtmlMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmation(
            String recipient,
            String customerName,
            String orderCode) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.net");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + orderCode + " ✅");

        String safeName = escapeHtml(customerName);
        String safeCode = escapeHtml(orderCode);

        String html = """
                <!doctype html>
                <html lang="vi">
                  <head><meta charset="UTF-8"></head>
                  <body>
                    <h1>Đơn hàng đã được xác nhận</h1>
                    <p>Xin chào, %s!</p>
                    <p>Mã đơn hàng: <strong>%s</strong></p>
                  </body>
                </html>
                """.formatted(safeName, safeCode);

        helper.setText(html, true);
        mailSender.send(message);
    }

    private static String escapeHtml(String value) {
        return value
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
~~~

Ví dụ dùng Java text block và String.formatted (cần phiên bản Java hỗ trợ, chẳng hạn Java 17). Các điểm chính:

- **createMimeMessage()** tạo đối tượng tương thích với sender.
- **MimeMessageHelper(message, false, "UTF-8")** chỉ định encoding; false phù hợp với một part HTML đơn giản chưa có attachment.
- **setSubject** nhận Unicode, thư viện thực hiện header encoding khi serialize.
- **setText(html, true)** đánh dấu nội dung là HTML.
- **escapeHtml** xử lý dữ liệu người dùng trước khi chèn vào template; nó không thay UTF-8 hay transfer encoding.
- **send()** thực hiện SMTP submission; khi server chấp nhận thư vẫn chưa có bằng chứng người nhận đã đọc.

Khi sử dụng template engine như Thymeleaf, nên dùng chức năng escape theo ngữ cảnh của template thay vì ghép HTML bằng chuỗi. Template phải được render thành chuỗi Unicode đúng, sau đó chuyển cho setText(..., true).
## 8. Email có cả text/plain và text/html

Email HTML thường nên có phiên bản **text/plain** để hỗ trợ email client không render HTML, công cụ đọc màn hình hoặc hệ thống lọc nội dung. MIME dùng kiểu **multipart/alternative** để đóng gói nhiều biểu diễn của cùng một nội dung.

~~~text
multipart/alternative
  |
  +-- text/plain; charset=UTF-8
  |     Content-Transfer-Encoding: ...
  |
  +-- text/html; charset=UTF-8
        Content-Transfer-Encoding: ...
~~~

Hai part có thể dùng transfer encoding khác nhau, nhưng nên thống nhất **nội dung có nghĩa** và khai báo charset đúng. Ví dụ cùng một thông báo phải hiển thị chữ tiếng Việt đúng cả khi người đọc chọn HTML lẫn khi hệ thống chỉ hiện plain text.

Với **MimeMessageHelper**, có thể cung cấp hai phiên bản:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class AlternativeBodyMail {
    private final JavaMailSender mailSender;

    public AlternativeBodyMail(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        // Dùng multipart khi tạo các part thay thế.
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom("notifications@example.net");
        helper.setTo(recipient);
        helper.setSubject("Thông báo mới – đơn hàng #123");

        String plain = """
                Xin chào!
                Đơn hàng #123 của bạn đã được xác nhận.
                Cảm ơn bạn đã sử dụng dịch vụ.
                """;

        String html = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <h1>Xin chào!</h1>
                    <p>Đơn hàng <strong>#123</strong>
                       của bạn đã được xác nhận.</p>
                    <p>Cảm ơn bạn đã sử dụng dịch vụ.</p>
                  </body>
                </html>
                """;

        helper.setText(plain, html);
        mailSender.send(message);
    }
}
~~~

Trong ví dụ, **setText(plain, html)** biểu diễn hai phiên bản của cùng thông báo. Khi được xây dựng với multipart mode, helper có thể tổ chức các part theo **cấu trúc multipart lồng nhau** phù hợp với implementation. Không nên mặc định part plain nằm ở vị trí index 0 của multipart ngoài cùng trong mọi trường hợp; hãy kiểm tra Content-Type/part thực tế nếu cần phân tích.

Khi email còn có **attachment hoặc inline image**, cấu trúc MIME có thể lồng **multipart/mixed**, **multipart/related** và **multipart/alternative**. Các body part vẫn phải có charset và transfer encoding phù hợp, bất kể chúng nằm sâu trong cây MIME.

### Không dùng một chuỗi HTML làm plain text

Đoạn:

~~~java
helper.setText("<p>Xin chào!</p>", false);
~~~

được hiểu là text/plain và người nhận có thể thấy cả ký tự thẻ HTML. Ngược lại:

~~~java
helper.setText("<p>Xin chào!</p>", true);
~~~

đánh dấu body là text/html. Tham số boolean ở đây là **cờ HTML**, không phải cờ bật/tắt UTF-8. Charset được cung cấp riêng khi dựng helper.

## 9. SimpleMailMessage và văn bản thuần tiếng Việt

Không phải email nào cũng cần MimeMessageHelper. Khi chỉ có subject và body text, **SimpleMailMessage** thường đủ:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public class PlainTextMailService {
    private final JavaMailSender sender;

    public PlainTextMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("noreply@example.net");
        mail.setTo(recipient);
        mail.setSubject("Lịch hẹn ngày mai");
        mail.setText("Xin chào! Lịch hẹn của bạn đã được xác nhận.");
        sender.send(mail);
    }
}
~~~

Với JavaMailSenderImpl, quá trình gửi SimpleMailMessage sẽ chuyển sang hình thức MIME phù hợp trước khi gửi qua SMTP. Khi cần Unicode, nên có **default encoding UTF-8** trên sender. Nếu project dùng nhiều JavaMailSender bean, phải bảo đảm sender thực sự được inject là sender đã cấu hình đúng.

So sánh:

| Tình huống | Cách làm phù hợp |
|---|---|
| Text thông báo ngắn có tiếng Việt | SimpleMailMessage và sender default UTF-8 |
| HTML với tag, CSS inline | MimeMessageHelper.setText(html, true) |
| Có cả text/plain và text/html | MimeMessageHelper.setText(plain, html) trong multipart |
| Attachment, ảnh inline, cấu trúc MIME phức tạp | MimeMessage với multipart và helper |
| Cần kiểm soát header/part đặc thù | Jakarta Mail API cùng quy tắc MIME tương ứng |

**Không phải nội dung có tiếng Việt là bắt buộc dùng HTML**. Text/plain với UTF-8 cũng thể hiện đầy đủ tiếng Việt và thường là lựa chọn tốt cho thông báo ngắn.

## 10. Tên người gửi, địa chỉ và tên attachment cũng có encoding riêng

Chỉ sửa Subject/body chưa chắc làm mọi phần của email hiển thị đúng. Những vùng khác cần được xử lý riêng:

- **Display name**: phần tên hiển thị ở From, ví dụ “Bộ phận Chăm sóc khách hàng”; đây là một thành phần header.
- **Email address**: mailbox có quy tắc cú pháp riêng; không thể coi toàn bộ địa chỉ là một đoạn subject UTF-8.
- **Attachment filename**: tên file trong MIME header có quy tắc mã hóa tham số riêng, có thể liên quan RFC 2231 và hành vi tương thích của client.
- **Reply-To, To, Cc**: phần tên hiển thị có thể Unicode, trong khi địa chỉ phải tuân thủ khả năng của server và giao thức.

Ví dụ đặt display name Unicode:

~~~java
import jakarta.mail.internet.InternetAddress;

helper.setFrom(new InternetAddress(
        "support@example.net",
        "Bộ phận Hỗ trợ Khách hàng",
        "UTF-8"));
~~~

Constructor InternetAddress này nhận địa chỉ, personal name và charset cho personal name. Jakarta Mail sẽ biểu diễn display name phù hợp khi serialize header. Không nên tự thêm Base64 vào địa chỉ hoặc trực tiếp nối tên Unicode vào chuỗi header rồi bỏ qua API.

Ví dụ attachment tên tiếng Việt:

~~~java
import org.springframework.core.io.FileSystemResource;

helper.addAttachment(
        "Báo cáo tháng 11.pdf",
        new FileSystemResource("/var/reports/report.pdf"));
~~~

Tên file là **metadata trong MIME header**, còn byte nội dung file thường được thể hiện bằng Content-Transfer-Encoding riêng, chẳng hạn Base64. Các email client không phải lúc nào cũng xử lý tham số tên file Unicode giống nhau, đặc biệt hệ thống cũ. Nếu lỗi chỉ xuất hiện ở tên attachment, cần xem header Content-Disposition/Content-Type thực tế và lựa chọn cấu hình tương thích; không nên đổi charset của toàn HTML body để sửa một header filename.

### Charset của Subject khác với internationalized email address

Một subject có dấu tiếng Việt có thể được mã hóa thành RFC 2047 encoded-word ngay cả khi SMTP server chỉ hỗ trợ địa chỉ ASCII. Nhưng **địa chỉ email có ký tự Unicode trong local-part** là vấn đề khác; việc truyền địa chỉ kiểu đó có thể cần hỗ trợ **SMTPUTF8** theo các mở rộng liên quan đến email quốc tế hóa. Tên miền quốc tế hóa cũng có quy tắc IDNA riêng.

Do đó, **đặt subject=UTF-8 không tự động cho phép mọi địa chỉ email Unicode**. Cần kiểm tra tính hợp lệ của địa chỉ và khả năng hỗ trợ của SMTP provider trước khi dùng địa chỉ quốc tế hóa.

## 11. Không nhầm charset lỗi với HTML injection

Giả sử một người dùng đặt tên:

~~~text
An <script>alert("x")</script>
~~~

Nếu ghép trực tiếp tên này vào body HTML, email client có thể xử lý nó như markup, tùy cơ chế lọc và render. Đây là vấn đề **escape/validate dữ liệu đầu vào**, không phải vấn đề UTF-8. Khi muốn hiển thị đúng nguyên văn, dữ liệu phải được escape cho ngữ cảnh HTML text node:

~~~html
<p>Xin chào, An &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</p>
~~~

Nếu chèn vào **HTML attribute** như href, src, title hoặc style, còn phải xử lý theo **ngữ cảnh attribute/URL/CSS**. Không nên lấy hàm escape text node rồi coi như giải pháp an toàn cho mọi nơi. Tốt nhất sử dụng template engine có chức năng escape tự động cho ngữ cảnh phù hợp.

### Subject và header injection

Subject là header, không phải HTML. Ký tự CR/LF do người dùng cung cấp có thể gây **header injection** nếu ứng dụng hoặc thư viện xử lý không đúng. Với phần Subject động:

~~~java
public static String requireSingleLineSubject(String subject) {
    if (subject == null || subject.isBlank()) {
        throw new IllegalArgumentException("Subject is required");
    }
    if (subject.indexOf('\r') >= 0 || subject.indexOf('\n') >= 0) {
        throw new IllegalArgumentException(
                "Subject must not contain CR or LF");
    }
    return subject;
}
~~~

Kết hợp với giới hạn độ dài và chính sách nội dung nếu cần. Việc dùng MimeMessageHelper giúp thư viện xử lý mã hóa header chuẩn, nhưng **không thay thế việc validate dữ liệu không đáng tin** hoặc việc ngăn người dùng điều khiển trái phép các header người nhận.

### Unicode normalization và emoji

Một ký tự nhìn giống nhau có thể có nhiều cách biểu diễn Unicode, ví dụ ký tự có dấu được lưu thành một code point tổ hợp sẵn hoặc base character + combining mark. UTF-8 có thể mã hóa cả hai cách nhưng kết quả byte khác nhau. Nếu ứng dụng so sánh, tìm kiếm hoặc ký nội dung theo byte, có thể cân nhắc **Unicode normalization** theo chính sách của hệ thống.

Không được dùng normalization tùy tiện cho mọi dữ liệu: token, chữ ký số hoặc các chuỗi có ý nghĩa chính xác theo byte có thể bị thay đổi. Emoji còn có thể chứa nhiều code point và variation selector; độ dài Java String, số code point và số ký tự người dùng nhìn thấy **không giống nhau**. Việc chỉ đặt UTF-8 giúp giữ byte, nhưng **font và khả năng render của email client** vẫn quyết định biểu tượng hiển thị ra sao.

## 12. Dữ liệu sai có thể đến từ nơi khác trước khi gửi mail

Một pipeline thực tế:

~~~text
HTTP request / database / template resource
        |
        v
Application/domain Java String
        |
        v
Template rendering HTML
        |
        v
MimeMessageHelper + Jakarta Mail
        |
        v
SMTP transport
        |
        v
Email client
~~~

Nếu nguồn là file template, hãy đọc bằng charset chính xác:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String html = Files.readString(
        Path.of("templates/email/welcome.html"),
        StandardCharsets.UTF_8);
~~~

Đây là ví dụ đọc từ đường dẫn filesystem; trong ứng dụng Spring Boot đóng gói thành JAR, template thường nằm trong **classpath** và nên được đọc qua resource/template engine phù hợp, thay vì giả định một đường dẫn vật lý tồn tại.

Một lỗi phổ biến là chuyển chuỗi Unicode thành bytes với charset mặc định, rồi dựng lại String bằng charset khác:

~~~java
// Không nên làm: có nguy cơ làm sai dữ liệu Unicode.
byte[] bytes = original.getBytes();  // Phụ thuộc charset mặc định.
String wrong = new String(bytes, StandardCharsets.ISO_8859_1);
~~~

Khi xử lý byte để tích hợp với hệ thống ngoài, hãy chỉ định rõ charset của **bên tạo byte** và **bên đọc byte**. Nếu dữ liệu đã biến thành dấu hỏi ở tầng database hoặc API, cấu hình MimeMessageHelper=UTF-8 chỉ bảo toàn những dấu hỏi đó, không thể phục hồi chữ gốc.

Trong các hệ thống dùng JDBC/JPA, nên kiểm tra encoding kết nối/column/database theo hệ quản trị thực tế và cách driver ánh xạ Unicode. Với message broker, template renderer hoặc một dịch vụ HTTP upstream, cần biết chúng gửi chuỗi Unicode hay byte và charset được khai báo ở ranh giới đó.
## 13. Xem raw MIME để phân biệt lỗi mã hóa và lỗi hiển thị

Khi người dùng báo email sai dấu, chỉ nhìn giao diện email client chưa đủ để xác định nguyên nhân. Có thể kiểm tra **nguyên bản MIME source** của thông điệp trong SMTP sink ở local/staging hoặc qua tính năng xem nguồn của email client, nếu được phép.

Ví dụ một thông điệp:

~~~mime
From: notifications@example.net
To: recipient@example.org
Subject: =?UTF-8?B?Q2Fmw6k=?=
MIME-Version: 1.0
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<html><body><p>Xin ch=C3=A0o, Caf=C3=A9!</p></body></html>
~~~

Email client phù hợp sẽ decode thành:

~~~text
Subject: Café
Body: Xin chào, Café!
~~~

Nếu raw source khai báo **Content-Type: text/html; charset=US-ASCII** nhưng body mang byte UTF-8 không được biểu diễn đúng, cần kiểm tra chặng tạo MIME. Nếu raw source đã chứa dấu hỏi thay cho chữ tiếng Việt ngay trước khi encode, dữ liệu có thể đã hỏng từ nguồn. Nếu raw MIME có dữ liệu đúng nhưng một client cụ thể hiển thị sai, cần kiểm tra khả năng giải mã MIME và render của client hoặc các biến đổi do hạ tầng trung gian.

### Không đọc toàn bộ raw MIME như một file văn bản UTF-8

Một MIME message có thể chứa nhiều part với charset và transfer encoding **khác nhau**. Đọc toàn bộ raw message thành một String UTF-8 rồi tìm chữ tiếng Việt chưa chắc đúng, vì body có thể ở Base64 hoặc quoted-printable. **Đọc từng MIME part bằng Jakarta Mail** giúp thư viện decode Content-Transfer-Encoding và charset tương ứng.

Trong một ngữ cảnh chẩn đoán được kiểm soát, có thể xem subject đã decode và header raw:

~~~java
String decodedSubject = message.getSubject();
String rawSubject = message.getHeader("Subject", null);

System.out.println("Decoded Subject: " + decodedSubject);
System.out.println("Raw Subject: " + rawSubject);
~~~

**Không tự động log Subject, người nhận hay nội dung mail ở production** nếu chúng chứa dữ liệu cá nhân. Đây chỉ là ví dụ chẩn đoán trong môi trường thử nghiệm.

### SMTP sink giúp quan sát MIME

Một SMTP sink như môi trường local/test có thể capture message mà không gửi tới địa chỉ ngoài. Có thể xem:

~~~text
Spring Mail service
    |
    v
SMTP sink / test server
    |
    +-- Raw MIME source
    +-- Decoded subject
    +-- text/plain preview
    +-- text/html preview
    +-- Attachment metadata
~~~

Hãy dùng dữ liệu giả hoặc đã khử nhạy cảm. Sink có thể lưu toàn bộ nội dung và attachment, do đó cần hạn chế truy cập vào giao diện quản trị.

## 14. Test round-trip Subject và body UTF-8

Có thể kiểm tra việc **dựng MIME** mà không cần SMTP server: tạo MimeMessage, serialize thành byte, parse lại rồi assert **giá trị Unicode đã decode**. Cách này cho thấy chuỗi sống sót qua bước encode/decode của thư viện.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

class VietnameseMimeEncodingTest {
    @Test
    void preservesVietnameseSubjectAndHtmlBody() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());
        helper.setFrom("notifications@example.net");
        helper.setTo("alice@example.org");
        helper.setSubject("Thông báo mới – cảm ơn bạn ✅");
        helper.setText(
                "<html><body><p>Xin chào, bạn nhé! ✅</p></body></html>",
                true);

        message.saveChanges();
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        message.writeTo(bytes);

        MimeMessage parsed = new MimeMessage(
                session,
                new ByteArrayInputStream(bytes.toByteArray()));

        assertEquals(
                "Thông báo mới – cảm ơn bạn ✅",
                parsed.getSubject());
        assertTrue(parsed.isMimeType("text/html"));
        assertTrue(
                ((String) parsed.getContent())
                    .contains("Xin chào, bạn nhé! ✅"));
    }
}
~~~

Những điều quan trọng trong ví dụ:

1. **saveChanges()** hoàn tất metadata MIME cần thiết trước serialize.
2. **writeTo(...)** tạo byte của message, bao gồm header và body transfer encoding.
3. Một MimeMessage thứ hai được tạo từ byte; kiểm tra **round-trip** thay vì chỉ đọc cùng object Java ban đầu.
4. **getSubject()** trả header đã được Jakarta Mail decode.
5. **getContent()** của part text/html đơn giản có thể trả String đã được decode theo Content-Type và Content-Transfer-Encoding.

Test này **không kiểm tra SMTP connection hay inbox delivery**. Nó tập trung vào cách xây dựng MIME. Với cấu trúc multipart/alternative hoặc attachment, getContent có thể trả **Multipart**; khi đó cần duyệt các body part và tìm text/plain hoặc text/html qua phương thức **isMimeType(...)**, thay vì ép toàn message về String.

### Không khóa test vào một raw Base64 cố định

Đừng giả định mọi phiên bản thư viện sẽ luôn chọn cùng cách gấp dòng, cùng chuyển đổi header hay cùng Content-Transfer-Encoding khi các cách đều hợp lệ. Những assertion quan trọng hơn:

- Subject sau decode giữ đúng Unicode.
- Part có Content-Type và charset mong đợi.
- Body sau decode có đúng ký tự và nội dung.
- Dữ liệu HTML động được escape đúng theo ngữ cảnh.
- Plain/HTML alternative có cùng thông tin cần thiết.

Khi mục tiêu là kiểm tra **SMTP transport, STARTTLS, SMTP AUTH hoặc client cụ thể**, cần một integration test trong môi trường được phép, ví dụ SMTP sink hoặc tài khoản thử nghiệm. Mock JavaMailSender chỉ xác nhận lời gọi mock, không chứng minh dữ liệu MIME thực tế.
## 15. Các triệu chứng thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Subject sai dấu, body đúng | Header encoding sai hoặc đã encode trước | Dùng setSubject nhận Unicode, xem raw Subject |
| Subject đúng, HTML body sai | Charset text/html không khớp byte hoặc nguồn template lỗi | Xem MIME Content-Type, transfer encoding và dữ liệu nguồn |
| Plain text đúng, HTML sai | Hai part được tạo từ các nguồn/charset khác nhau | Inspect từng part và encoding của helper |
| HTML đúng, plain text sai | Plain part bị dựng sai nội dung hoặc charset | Xem hai đối số của setText(plain, html) |
| Người nhận thấy =?UTF-8?B?...?= | Có thể double-encoding Subject hoặc email client decode lỗi | Không tự encode trước setSubject |
| Người nhận thấy =C3=A0 trong body | Có thể thiếu hoặc sai Content-Transfer-Encoding header | Đối chiếu raw body với khai báo của part |
| Có ký tự thay thế � hoặc dấu ? | Byte đã decode sai hoặc bị mất dữ liệu từ trước | Kiểm tra HTTP, database, template, sau đó mới đến MIME |
| Email hiển thị nguyên thẻ HTML | Body bị gửi như text/plain | Gọi setText(html, true) |
| Nội dung hiển thị &amp;lt; thay vì < | HTML có thể bị escape hai lần | Kiểm tra pipeline render và escape |
| Tên From bị lỗi nhưng subject đúng | Encoding display name ở header | Dùng InternetAddress với charset phù hợp |
| Tên attachment tiếng Việt bị lỗi | Cách encode MIME filename hoặc hỗ trợ của client | Xem Content-Disposition/Content-Type header thực tế |
| Emoji thành ô vuông | Font/client thiếu glyph hoặc dữ liệu gốc đã bị thay | Kiểm tra round-trip Unicode và client render |
| Một client sai, các client khác đúng | Khả năng render/MIME decoder khác nhau hoặc biến đổi trung gian | So sánh MIME gốc và MIME ở phía nhận |

Một quá trình xử lý hiệu quả:

~~~mermaid
flowchart TD
    A[Email hiển thị sai dấu] --> B{Java String trước khi tạo email đúng chưa?}
    B -- Không --> C[Kiểm tra HTTP / DB / template / charset nguồn]
    B -- Có --> D[Capture MIME đã serialize]
    D --> E{Header/part có charset phù hợp?}
    E -- Không --> F[Kiểm tra helper và sender configuration]
    E -- Có --> G{Parse lại MIME bằng Jakarta Mail đúng?}
    G -- Không --> H[Kiểm tra encoding và dữ liệu part]
    G -- Có --> I[So sánh MIME ở client hoặc relay]
    I --> J[Kiểm tra biến đổi trung gian hoặc render của client]
~~~

**Xác định lỗi xuất hiện ở chặng nào** sẽ hiệu quả hơn việc đổi ngẫu nhiên charset từ UTF-8 sang ISO-8859-1 rồi thử lại. Nếu đổi charset làm một đoạn văn được nhưng đoạn khác sai, có thể dữ liệu nguồn vốn đã bị trộn nhiều kiểu encoding.

## 16. Một số tình huống nâng cao cần lưu ý

### Header Subject dài có thể được gấp dòng

Email header có quy tắc giới hạn độ dài dòng, do đó thư viện có thể phân chia subject thành nhiều encoded-word hoặc chèn CRLF cùng whitespace. Đây là hành vi **header folding** bình thường. Khi inspect raw source, không nên nối các dòng bằng cách loại bỏ tùy tiện ký tự hoặc xử lý Base64 từng mẩu theo suy đoán; Jakarta Mail đã có logic parse/giải mã header.

### MIME body có thể được gấp dòng dù text ban đầu không có xuống dòng

Quoted-printable có thể dùng dấu **=** ở cuối dòng để báo **soft line break**. Base64 cũng được gấp dòng thành các nhóm ký tự theo quy tắc MIME. Các dấu xuống dòng phục vụ encoding này **không nhất thiết là dấu xuống dòng mà người đọc sẽ thấy** sau giải mã.

~~~mime
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

This is a long line that may be split using a soft line break =
without inserting a visible newline in the decoded content.
~~~

Khi nội dung được decode, dấu xuống dòng mềm không trở thành ký tự xuống dòng của văn bản. Vì vậy, khi đối chiếu raw email và Java String, không nên lấy số dòng raw làm bằng chứng body có thêm newline.

### Nội dung HTML và CSS không chỉ phụ thuộc charset

Một HTML body có thể chứa tiếng Việt chuẩn UTF-8 nhưng vẫn render khác nhau giữa Gmail và Outlook do mức hỗ trợ CSS, font, dark mode hoặc ảnh từ xa. Các vấn đề này thuộc **khả năng render email client**, không phải lỗi mã hóa ký tự. Cần tách kết quả **decode đúng Unicode** khỏi **hiển thị giao diện giống nhau**.

### Kích thước sau encoding có thể thay đổi

UTF-8 dùng số byte khác nhau cho từng ký tự; tiếng Việt thường cần nhiều byte hơn ASCII, emoji có thể cần bốn byte cho một code point. Base64 và quoted-printable có thể làm MIME body dài hơn chuỗi nội dung ban đầu. Khi gửi mail kèm HTML dài hoặc attachment, cần so sánh **kích thước MIME đã encode** với giới hạn SMTP provider, không chỉ lấy Java String.length().

### Charset UTF-8 không giải quyết tính toàn vẹn hay bảo mật transport

UTF-8 cho biết cách biểu diễn ký tự, không mã hóa bí mật. Email có thể bị đọc nếu kênh/hạ tầng không được bảo vệ. Sử dụng STARTTLS/TLS, chính sách xác thực và quyền gửi phù hợp là một chủ đề riêng, bổ sung cho encoding. Đồng thời **HTML escaping** giúp tránh đưa markup không tin cậy vào nội dung, nhưng không bảo vệ secret lưu trong email.

### Email có nhiều ngôn ngữ

UTF-8 hỗ trợ tiếng Việt, tiếng Anh, Nhật, Hàn và nhiều hệ chữ khác trong cùng một message, không cần chọn mỗi ngôn ngữ một charset riêng. Có thể đặt thuộc tính lang phù hợp trong HTML để hỗ trợ công nghệ trợ năng và gợi ý phát âm:

~~~html
<html lang="vi">
  <body>
    <p>Chào bạn!</p>
    <p lang="en">Thank you for your order.</p>
  </body>
</html>
~~~

Tuy nhiên, một vài hệ chữ hoặc emoji vẫn cần font tương ứng phía email client. Việc byte đúng chỉ là điều kiện cần, không bảo đảm glyph hiển thị như bản thiết kế.

## 17. Cách phối hợp các API trong Spring Mail

Để tránh nhầm lẫn giữa Subject, body và HTML, có thể chọn API theo nhu cầu:

| Nhu cầu | API thường dùng | Điểm cần chú ý |
|---|---|---|
| Email text đơn giản | SimpleMailMessage + JavaMailSender | Sender có default encoding UTF-8 |
| Subject tiếng Việt | MimeMessageHelper.setSubject(String) | Truyền Unicode trực tiếp, không tự Base64 |
| Body text thuần | MimeMessageHelper.setText(text, false) | Charset UTF-8 cho text/plain |
| Body HTML | MimeMessageHelper.setText(html, true) | Charset UTF-8, escape dữ liệu động |
| Plain text + HTML | MimeMessageHelper.setText(plain, html) | Chọn multipart thích hợp, kiểm tra cả hai part |
| Tên người gửi có dấu | InternetAddress(address, personal, charset) | Header encoding riêng với địa chỉ mailbox |
| Attachment tên Unicode | MimeMessageHelper.addAttachment(...) | Xem encoding filename khi có vấn đề tương thích |
| Test mã hóa không kết nối SMTP | MimeMessage.writeTo + parse lại | Assert nội dung sau decode, không chỉ raw source |

Một luồng tạo email đúng nghĩa:

~~~text
1. Nhận dữ liệu Unicode đúng từ application layer.
2. Render template HTML có escaping theo ngữ cảnh.
3. Tạo MimeMessage bằng JavaMailSender.
4. Tạo MimeMessageHelper với charset UTF-8 rõ ràng.
5. Đặt From/To, Subject bằng API header tương ứng.
6. Đặt text/plain và/hoặc text/html phù hợp với MIME.
7. Để Jakarta Mail tạo Content-Type và transfer encoding.
8. Gửi qua SMTP; xử lý lỗi submission riêng với delivery.
~~~

Ví dụ khung:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("notifications@example.net");
helper.setTo("alice@example.org");
helper.setSubject("Xin chào – thông báo của bạn");
helper.setText(
        "Xin chào! Đây là thông báo dạng văn bản.",
        "<html lang=\"vi\"><body><p>Xin chào!</p>"
                + "<p>Đây là <strong>thông báo</strong> HTML.</p>"
                + "</body></html>");

mailSender.send(message);
~~~

**Nguyên tắc cốt lõi:** Subject thuộc lớp **MIME header**; text/plain và text/html thuộc lớp **MIME body**; UTF-8 mô tả byte của văn bản, Content-Transfer-Encoding mô tả cách truyền byte, còn HTML escaping xử lý cú pháp của nội dung. Trong Spring Framework Mail, dùng **MimeMessageHelper với UTF-8**, truyền chuỗi Unicode chưa encode vào setSubject/setText, và kiểm tra kết quả bằng **MIME round-trip** khi có lỗi ký tự. Đó là cách bảo toàn tiếng Việt và nội dung đa ngôn ngữ nhất quán qua email.
