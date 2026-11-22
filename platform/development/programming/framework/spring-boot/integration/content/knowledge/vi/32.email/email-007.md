# Mẫu thư, bản địa hóa và mã hóa ký tự

## 1. Vì sao email cần cả template, bản địa hóa và mã hóa?

Trong một ứng dụng **Spring Boot Integration**, email thường là bước cuối của một luồng nghiệp vụ: xác nhận tài khoản, đặt lại mật khẩu, thông báo đơn hàng, gửi hóa đơn hoặc cảnh báo vận hành. Người nhận cần nhận được **đúng nội dung, đúng ngôn ngữ và đúng ký tự**, bất kể máy chủ SMTP hay ứng dụng đọc thư đang dùng môi trường nào.

Ba mối quan tâm này có vai trò khác nhau:

| Thành phần | Giải quyết vấn đề | Ví dụ |
| --- | --- | --- |
| **Mẫu thư (template)** | Tách cấu trúc trình bày khỏi mã xử lý nghiệp vụ. | Một mẫu `welcome.html` nhận tên người dùng và liên kết xác nhận. |
| **Bản địa hóa (localization / i18n)** | Chọn bản dịch, định dạng ngày giờ, số tiền theo người nhận. | “Xác nhận tài khoản” cho `vi`; “Confirm account” cho `en`. |
| **Mã hóa ký tự (character encoding)** | Biểu diễn và truyền tải tiếng Việt, ký tự đặc biệt, emoji qua MIME/SMTP. | “Trần Ánh”, “Đơn hàng”, “🎉” không bị biến thành dấu hỏi hoặc ký tự lỗi. |

Không nên nhúng nguyên HTML, bản dịch và cấu hình SMTP vào cùng một phương thức gửi thư. Một luồng điển hình là:

~~~mermaid
flowchart LR
    A[Ứng dụng phát sinh sự kiện] --> B[Chọn người nhận và Locale]
    B --> C[Nạp thông điệp bản địa hóa]
    C --> D[Render template với dữ liệu]
    D --> E[Tạo MIME: text/plain và text/html, UTF-8]
    E --> F[JavaMailSender]
    F --> G[SMTP và hộp thư người nhận]
~~~

Ở đây, **Spring Boot** cấu hình SMTP và tạo `JavaMailSender`; **Thymeleaf** dựng phần HTML; **MessageSource** lấy câu chữ theo `Locale`; **Jakarta Mail** tạo nội dung MIME và các header. Các ví dụ dưới đây dùng phong cách Spring Boot 3+ với `jakarta.mail`.

## 2. Chuẩn bị dependencies và cấu hình

Với Maven, cần dependency gửi thư và engine dựng template:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ `application.properties`:

~~~properties
spring.mail.host=smtp.example.net
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

spring.messages.basename=messages/email
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false

app.mail.from=no-reply@example.net
~~~

`SMTP_USERNAME` và `SMTP_PASSWORD` được cấp qua biến môi trường hoặc hệ thống quản lý bí mật; không đưa mật khẩu thật vào kho mã nguồn. Địa chỉ `smtp.example.net` chỉ là ví dụ, cần thay bằng nhà cung cấp SMTP của hệ thống. Cấu hình trên sử dụng STARTTLS ở cổng 587; máy chủ dùng TLS ngầm định ở cổng 465 cần cấu hình SSL/TLS tương ứng theo nhà cung cấp. Các timeout tránh giữ luồng gửi thư vô thời hạn khi mạng gặp sự cố.

Khi dùng Thymeleaf cùng cơ chế tự cấu hình của Spring Boot, mẫu HTML mặc định được tìm trong `src/main/resources/templates/`. Cần quyết định rõ ai sở hữu địa chỉ `From`, tên người gửi, tên thương hiệu và từng phiên bản ngôn ngữ.

## 3. Tổ chức mẫu thư và tài nguyên ngôn ngữ

Một cấu trúc đơn giản, có thể mở rộng cho nhiều loại email:

~~~text
src/main/resources/
├── templates/
│   └── mail/
│       └── welcome.html
└── messages/
    ├── email.properties
    └── email_vi.properties
~~~

`email.properties` đóng vai trò bản tiếng Anh mặc định khi không tìm thấy bản dịch phù hợp. Ví dụ:

~~~properties
mail.from.name=Example Shop
mail.welcome.subject=Welcome to Example Shop
mail.welcome.title=Welcome!
mail.welcome.greeting=Hello {0},
mail.welcome.intro=Please confirm your email address to activate your account.
mail.welcome.action=Confirm account
mail.welcome.signature=The Example Shop team
mail.welcome.plain=Hello {0}. Confirm your account at: {1}
~~~

`email_vi.properties` chứa bản dịch tiếng Việt:

~~~properties
mail.from.name=Cửa hàng Ví Dụ
mail.welcome.subject=Chào mừng bạn đến với Cửa hàng Ví Dụ
mail.welcome.title=Chào mừng bạn!
mail.welcome.greeting=Xin chào {0},
mail.welcome.intro=Vui lòng xác nhận địa chỉ email để kích hoạt tài khoản của bạn.
mail.welcome.action=Xác nhận tài khoản
mail.welcome.signature=Đội ngũ Cửa hàng Ví Dụ
mail.welcome.plain=Xin chào {0}. Hãy xác nhận tài khoản tại: {1}
~~~

Hai file này phải được lưu **UTF-8**. Với cấu hình `spring.messages.basename=messages/email`, `MessageSource` đọc các khóa này theo `Locale`. Tham số `{0}`, `{1}` được thay bằng dữ liệu ở lúc render, nhờ đó không cần nối chuỗi thủ công. Nếu một bản dịch có tham số định dạng kiểu `MessageFormat`, dấu nháy đơn trong bản dịch có thể phải viết thành `''`; cần kiểm thử các câu tiếng Anh chứa apostrophe.

Một mẫu HTML `templates/mail/welcome.html`:

~~~html
<!doctype html>
<html lang="en"
      xmlns:th="http://www.thymeleaf.org"
      th:lang="${#locale.language}">
<head>
    <meta charset="UTF-8">
    <title th:text="#{mail.welcome.subject}">Welcome</title>
</head>
<body>
    <h1 th:text="#{mail.welcome.title}">Welcome!</h1>
    <p th:text="#{mail.welcome.greeting(${customerName})}">Hello</p>
    <p th:text="#{mail.welcome.intro}">Please confirm your account.</p>
    <p>
        <a th:href="${confirmationUrl}"
           th:text="#{mail.welcome.action}">Confirm account</a>
    </p>
    <p th:text="#{mail.welcome.signature}">The team</p>
</body>
</html>
~~~

Trong Thymeleaf, `#{...}` tra thông điệp bản địa hóa, `${customerName}` đọc biến trong `Context` và `#{mail.welcome.greeting(${customerName})}` truyền tên vào tham số `{0}` của bản dịch. `th:text` tự escape ký tự HTML trong tên và nội dung nhập từ người dùng. Không dùng `th:utext` cho dữ liệu không đáng tin cậy; đưa HTML thô vào thư có thể tạo liên kết độc hại hoặc nội dung giả mạo. Liên kết trong `th:href` vẫn cần URL được ứng dụng kiểm tra và tạo từ domain đáng tin cậy.

Thực tế nên giữ email HTML gọn, dùng bảng bố cục hoặc CSS inline khi cần tương thích nhiều ứng dụng đọc thư. Không dựa vào JavaScript vì phần lớn trình đọc email không chạy script.

## 4. Chọn Locale theo người nhận, không theo máy chủ

`Locale` nên lấy từ ngôn ngữ người dùng đã chọn hoặc hồ sơ tài khoản. Chỉ khi chưa có lựa chọn này mới cân nhắc thông tin từ request như `Accept-Language`, sau đó áp chính sách ngôn ngữ hệ thống hỗ trợ.

Ví dụ ứng dụng hỗ trợ tiếng Việt và tiếng Anh:

~~~java
private static Locale supportedLocale(String languageTag) {
    Locale requested = Locale.forLanguageTag(
            languageTag == null ? "" : languageTag);
    if ("en".equals(requested.getLanguage())) {
        return Locale.ENGLISH;
    }
    return Locale.forLanguageTag("vi");
}
~~~

`en-US`, `en-GB` cùng chọn bản tiếng Anh; `vi-VN` và giá trị không được hỗ trợ chọn tiếng Việt theo chính sách ví dụ. Không lấy mặc định từ `Locale.getDefault()` của hệ điều hành: cùng một email có thể đổi ngôn ngữ khi triển khai sang máy chủ khác. Trong luồng gửi bất đồng bộ bằng `@Async`, queue hoặc Spring Integration, càng không nên giả định `LocaleContextHolder` còn giữ Locale từ HTTP request; hãy đưa mã ngôn ngữ vào lệnh gửi hoặc dữ liệu sự kiện.

Với ngày, giờ và số tiền, bản dịch chuỗi chưa đủ:

- Dùng `DateTimeFormatter` với `Locale` và **múi giờ người nhận hoặc múi giờ đã thống nhất**; một `Instant` có thể hiển thị khác ở mỗi khu vực.
- Dùng `NumberFormat`/`DecimalFormat` theo Locale nhưng giữ **đơn vị tiền tệ thực tế** từ giao dịch; không suy số tiền bằng đơn vị USD chỉ vì người dùng chọn tiếng Anh.
- Dịch cả văn bản thay thế liên kết, tên người gửi, thông báo lỗi và bản text thuần. Tránh ghép câu từ các mảnh dịch khiến thứ tự từ sai giữa các ngôn ngữ.

## 5. Dựng email HTML và text thuần bằng JavaMailSender

Đây là ví dụ dịch vụ có thể dùng cho email xác nhận tài khoản. Tham số `confirmationUrl` phải được ứng dụng tạo ở phía máy chủ, dùng HTTPS và token đủ mạnh, có hạn dùng. Ví dụ tập trung vào việc render và mã hóa nội dung; ở hệ thống thực cần kiểm tra người nhận và dữ liệu đầu vào ở lớp nghiệp vụ.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.UnsupportedEncodingException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.MessageSource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final MessageSource messageSource;
    private final String fromAddress;

    public WelcomeMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine,
            MessageSource messageSource,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
        this.messageSource = messageSource;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(
            String recipient,
            String customerName,
            String preferredLanguage,
            URI confirmationUrl) {

        Locale locale = supportedLocale(preferredLanguage);
        Context context = new Context(locale);
        context.setVariable("customerName", customerName);
        context.setVariable("confirmationUrl", confirmationUrl.toString());

        String html = templateEngine.process("mail/welcome", context);
        String plain = messageSource.getMessage(
                "mail.welcome.plain",
                new Object[] { customerName, confirmationUrl.toString() },
                locale);
        String subject = messageSource.getMessage(
                "mail.welcome.subject", null, locale);
        String senderName = messageSource.getMessage(
                "mail.from.name", null, locale);

        MimeMessage mime = mailSender.createMimeMessage();
        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mime,
                    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                    StandardCharsets.UTF_8.name());
            helper.setFrom(fromAddress, senderName);
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(plain, html);
        } catch (MessagingException | UnsupportedEncodingException ex) {
            throw new IllegalStateException("Cannot compose welcome email", ex);
        }

        mailSender.send(mime);
    }

    private static Locale supportedLocale(String languageTag) {
        Locale requested = Locale.forLanguageTag(
                languageTag == null ? "" : languageTag);
        return "en".equals(requested.getLanguage())
                ? Locale.ENGLISH
                : Locale.forLanguageTag("vi");
    }
}
~~~

Trong ví dụ:

1. `Context(locale)` gắn Locale vào template; `MessageSource` dùng cùng Locale cho tiêu đề, tên người gửi và phiên bản text.
2. `templateEngine.process("mail/welcome", context)` đọc `templates/mail/welcome.html`; dữ liệu như `customerName` chỉ là biến render.
3. `MimeMessageHelper` nhận charset `UTF-8` để tạo phần nội dung và header chứa tiếng Việt. `setFrom(fromAddress, senderName)` cho phép tên người gửi có dấu.
4. `setText(plain, html)` tạo hai dạng **text/plain** và **text/html** trong một thư MIME; ứng dụng đọc thư sẽ chọn dạng phù hợp. `MULTIPART_MODE_MIXED_RELATED` cho phép cấu trúc nhiều phần, bao gồm cả nội dung liên quan và tệp đính kèm nếu sau này cần.
5. `mailSender.send` gọi SMTP. Lỗi tạo MIME được bọc thành lỗi ứng dụng; lỗi vận chuyển của Spring Mail (như `MailSendException`) vẫn cần được tầng gửi thư xử lý theo cơ chế retry/giám sát.

Không nên chỉ gửi HTML: thư text thuần hỗ trợ trình đọc hạn chế, chế độ trợ năng, một số bộ lọc email và quá trình chẩn đoán. Hai phiên bản phải có cùng ý nghĩa, cùng liên kết và cùng ngôn ngữ.

## 6. UTF-8 và cấu trúc MIME: hiểu đúng để tránh lỗi dấu

SMTP truyền thông điệp theo định dạng MIME. Tách biệt **chuỗi Unicode trong Java** và **các byte được mã hóa để gửi đi** là chìa khóa chẩn đoán lỗi.

| Vị trí | Cách xử lý đúng | Lỗi thường gặp |
| --- | --- | --- |
| File `.properties` và `.html` | Lưu UTF-8; `spring.messages.encoding=UTF-8`. | File lưu sai bảng mã trước khi render, khiến `?` hoặc `Ã¡` xuất hiện. |
| Tiêu đề `Subject` | Gọi `helper.setSubject(subject)` với helper đã cấu hình UTF-8. | Tự gắn chuỗi Unicode vào header thô, không mã hóa theo MIME. |
| Tên hiển thị `From` | `helper.setFrom(email, displayName)`; thư viện xử lý phần tên Unicode. | Ghép thủ công `From: Tên có dấu <mail@...>`. |
| Nội dung text và HTML | `helper.setText(plain, html)` với charset UTF-8. | Chỉ đặt `<meta charset="UTF-8">` trong HTML nhưng MIME khai charset khác. |
| Ký tự đặc biệt trong HTML | `th:text` escape nội dung, `th:href` tạo thuộc tính từ URL đã kiểm soát. | Chèn trực tiếp dữ liệu người dùng vào markup hoặc URL. |
| Địa chỉ hộp thư | Kiểm tra tính hợp lệ và hỗ trợ của SMTP; ưu tiên local-part ASCII khi khả thi. | Nhầm Unicode trong tên hiển thị với yêu cầu SMTPUTF8 cho chính địa chỉ email. |

Một thông điệp có thể có dạng logic như sau (chỉ minh họa, ranh giới MIME thực do Jakarta Mail sinh):

~~~text
Subject: [header được MIME mã hóa khi cần]
From: [tên hiển thị được mã hóa] <no-reply@example.net>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary=...

  multipart/related
    multipart/alternative
      text/plain; charset=UTF-8
      text/html; charset=UTF-8
~~~

Tiêu đề và tên hiển thị có thể xuất hiện dưới dạng `=?UTF-8?B?...?=` hoặc `=?UTF-8?Q?...?=` trong header thô theo RFC 2047; trình đọc thư giải mã về chữ Unicode. Với nội dung, JavaMail có thể chọn `quoted-printable` hoặc `base64` làm `Content-Transfer-Encoding`. Đó là chuyện bình thường; không tự mã hóa Base64 hoặc thêm tiền tố RFC 2047 lần nữa trước khi gọi helper.

`Content-Type: ...; charset=UTF-8` của từng phần MIME mới là thông tin giải mã quyết định. Thẻ `<meta charset>` giúp một số trình đọc HTML nhưng **không thay thế** khai báo MIME. Không chuyển chuỗi qua `getBytes()` hoặc `new String(bytes)` mà bỏ qua charset khi tự xử lý tệp mẫu hay dữ liệu ngoại vi.

Nếu gửi tệp đính kèm, có thể gọi `helper.addAttachment(...)` sau khi đã thiết lập các phần nội dung, dùng `InputStreamSource`/`ByteArrayResource` và MIME type phù hợp. Không tự suy tên tệp từ dữ liệu người dùng không được kiểm soát; tệp lớn thường phù hợp với liên kết tải có kiểm soát hơn là đính kèm trực tiếp.

## 7. Thiết kế luồng tích hợp an toàn và dễ bảo trì

**Tách dữ liệu, nội dung và vận chuyển** giúp mở rộng từ email xác nhận tài khoản sang hóa đơn, OTP và thông báo trạng thái. Nên truyền vào service một đối tượng yêu cầu gửi gồm `recipient`, `templateKey`, `locale` và các biến đã được kiểm soát, thay vì tạo HTML trong controller. Mỗi mẫu cần version hoặc cách kiểm soát thay đổi khi nội dung pháp lý, liên kết, thương hiệu thay đổi.

Trong hệ thống có queue hoặc Spring Integration:

1. Giao dịch nghiệp vụ ghi trạng thái đơn hàng và một sự kiện gửi email (outbox nếu cần tính tin cậy).
2. Worker đọc sự kiện, chọn mẫu và ngôn ngữ theo dữ liệu được lưu cùng sự kiện/người nhận.
3. Worker dựng MIME và gửi qua SMTP; ghi trạng thái, số lần thử, mã lỗi và mã thông điệp theo dõi.
4. Retry khi lỗi tạm thời với backoff; định nghĩa khóa chống trùng để không gửi hai email khi worker hoặc SMTP retry sau timeout.

`JavaMailSender.send(...)` là thao tác I/O có thể chậm hoặc thất bại; không nên để lỗi SMTP làm sai kết quả của giao dịch đã ghi thành công. Đồng thời, SMTP chấp nhận một email chưa chắc có nghĩa email đã vào hộp thư chính: cần theo dõi bounce, complaint hoặc webhook từ nhà cung cấp nếu nghiệp vụ yêu cầu.

Với liên kết xác nhận/đặt lại mật khẩu, hãy phát sinh URL HTTPS trên domain được cấu hình, dùng token một lần có hạn, không ghi token vào log. Với email quảng bá, cần phân biệt nội dung giao dịch và nội dung tiếp thị, quản lý sự đồng ý và cơ chế hủy nhận theo yêu cầu áp dụng. Với dữ liệu cá nhân, giới hạn nội dung nhạy cảm trong tiêu đề và phần preview vì các nội dung này có thể xuất hiện trên màn hình khóa.

## 8. Kiểm thử và xử lý sự cố

Nên kiểm thử ở hai tầng: **render/MIME** không cần máy chủ SMTP thật và **gửi nhận tích hợp** qua SMTP thử nghiệm (ví dụ GreenMail hoặc môi trường sandbox của nhà cung cấp). Bộ kiểm thử tối thiểu:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Tên “Trần Thị Ánh”, bản `vi` | Tiêu đề, tên người gửi, nội dung HTML và text đều hiển thị đủ dấu. |
| `en-US` và `en-GB` | Chọn khóa tiếng Anh; không lẫn câu tiếng Việt ngoài nội dung dữ liệu riêng. |
| `fr-FR` hoặc không có preference | Áp chính sách fallback tiếng Việt đã định nghĩa trong `supportedLocale`. |
| Tên chứa `<b>`, `&` hoặc dấu nháy | HTML hiển thị đúng văn bản và không sinh thẻ HTML ngoài ý muốn. |
| Bản dịch thiếu một khóa | Phát hiện khóa chưa dịch hoặc fallback về bản cơ sở; kiểm tra đầy đủ key khi release. |
| Link xác nhận có query parameter | `href` hợp lệ, encode đúng, vẫn trỏ tới domain được phê duyệt. |
| Đọc MIME sau khi gửi thử | Tìm được cả `text/plain` và `text/html`; các phần text khai UTF-8. |
| SMTP timeout hoặc lỗi tạm thời | Có log/metric và retry theo chính sách; không tạo email trùng không kiểm soát. |

Khi kiểm tra bằng Jakarta Mail, `mimeMessage.getSubject()` thường cho giá trị Unicode **đã giải mã**, trong khi `getHeader("Subject")` là header thô đã mã hóa. Với multipart, phải đi qua các phần MIME để kiểm tra charset của `text/plain` và `text/html`; header `Content-Type` ở cấp gốc thường chỉ là `multipart/*`.

Một số hướng chẩn đoán cụ thể:

- **Chữ thành `Ã¡`, `á»` hoặc `?`**: kiểm tra byte gốc của file resource, cấu hình `MessageSource` và charset MIME; lỗi thường xảy ra trước khi gửi.
- **Đúng HTML nhưng sai Subject/From**: xem cách đặt header, đừng tự ghép header hoặc mã hóa Base64 bằng tay.
- **Đúng ở web nhưng sai trong email**: email client hỗ trợ HTML/CSS hạn chế; kiểm tra phiên bản text thuần, đường dẫn tuyệt đối HTTPS và CSS inline.
- **Worker gửi sai ngôn ngữ**: kiểm tra `Locale` đã được truyền cùng công việc hay chưa; đừng dựa vào trạng thái request thread.
- **Gửi thư bị trùng**: kiểm tra khóa idempotency, mốc xác nhận gửi và trường hợp timeout sau khi SMTP đã nhận thông điệp.

## 9. Nguyên tắc thực hành

Đối với các tích hợp email Spring Boot, một bài triển khai hoàn chỉnh có **template HTML**, **nội dung text thuần**, **bundle bản dịch được lưu UTF-8**, **Locale được lựa chọn có chủ đích**, **MIME charset UTF-8**, và **kịch bản kiểm thử thực tế với tiếng Việt**. Khi mở rộng sang nhiều ngôn ngữ, việc thêm một bundle và kiểm tra bản dịch sẽ thuận lợi hơn nhiều so với sửa Java cho từng câu chữ. Việc dựng thư tách khỏi việc gửi cũng giúp xử lý lỗi, retry và quan sát luồng tích hợp một cách nhất quán.
