# Tạo Content-ID ổn định trong một message

Khi gửi email HTML có hình ảnh hiển thị ngay trong nội dung, ứng dụng thường dùng **inline resource**. Một ví dụ quen thuộc là logo công ty, biểu tượng trạng thái hoặc hình minh họa nằm giữa các đoạn văn. HTML tham chiếu ảnh bằng một địa chỉ dạng `cid:...`, còn email chứa một MIME part có header `Content-ID` tương ứng.

Điều quan trọng là hai phía phải dùng **cùng một định danh**. Nếu template tạo `cid:logo-a` nhưng MIME part lại được gắn `Content-ID: <logo-b>`, mail client không thể liên kết ảnh với vị trí hiển thị. Nếu hai ảnh khác nhau dùng trùng Content-ID trong cùng message, kết quả cũng trở nên mơ hồ.

Trong Spring Framework Mail, `MimeMessageHelper.addInline(...)` giúp gắn resource vào message. Ứng dụng cần tạo Content-ID theo một quy tắc ổn định trong phạm vi message, truyền cùng giá trị đó vào template và helper, đồng thời bảo đảm các inline part khác nhau có ID riêng.

Bài học giải thích cấu trúc CID, phạm vi uniqueness, cách tạo ID theo từng message, cách dùng với Thymeleaf và `MimeMessageHelper`, cùng những lỗi thường gặp khi email có nhiều hình inline.

## 1. Content-ID là gì?

**Content-ID** là một header MIME dùng để định danh một phần nội dung trong message. Với hình ảnh inline, MIME part có thể chứa:

```text
Content-Type: image/png
Content-ID: <logo-7c9f2a@example.org>
Content-Disposition: inline
Content-Transfer-Encoding: base64
```

HTML trong body tham chiếu part đó:

```html
<img src="cid:logo-7c9f2a@example.org" alt="Logo công ty"/>
```

Hai biểu diễn có liên hệ:

| Vị trí | Giá trị minh họa | Vai trò |
| --- | --- | --- |
| MIME part header | `Content-ID: <logo-7c9f2a@example.org>` | Định danh của part |
| HTML attribute | `src="cid:logo-7c9f2a@example.org"` | Tham chiếu tới part theo Content-ID |

`cid:` là scheme của **Content-ID URI**. Mail client đọc HTML, tìm CID được tham chiếu và liên kết nó với MIME part có Content-ID tương ứng.

### Content-ID khác những định danh nào?

| Định danh | Phạm vi và mục đích |
| --- | --- |
| **Content-ID** | Định danh một MIME body part, ví dụ ảnh inline |
| **Message-ID** | Định danh toàn bộ email message |
| **Content-Location** | Có thể chỉ ra vị trí nội dung hoặc URI liên quan trong một số cấu trúc MIME |
| **Filename** | Tên hiển thị/lưu file, thường nằm trong Content-Disposition |
| **CID URI** | Cách HTML tham chiếu một MIME part bằng Content-ID |
| **URL HTTPS** | Tài nguyên được tải qua mạng từ một địa chỉ web |

Ví dụ, một email có thể có:

```text
Message-ID: <message-123@example.org>

Part 1:
  Content-Type: text/html; charset=UTF-8

Part 2:
  Content-Type: image/png
  Content-ID: <logo-456@example.org>
  Content-Disposition: inline
```

Message-ID nhận diện **toàn message**; Content-ID nhận diện **part chứa logo**. Không dùng Message-ID làm CID của tất cả hình trong email.

## 2. Content-ID phải ổn định và duy nhất như thế nào?

Có hai yêu cầu cần giữ cùng lúc:

1. **Ổn định trong một message:** giá trị được dùng trong HTML phải giống chính xác giá trị gắn vào MIME part.
2. **Duy nhất:** mỗi inline resource khác nhau cần một Content-ID riêng; theo quy tắc MIME, Content-ID được yêu cầu duy nhất trên phạm vi toàn cục.

RFC 2392 quy định Content-ID được dùng để tham chiếu MIME body part và yêu cầu giá trị Content-ID có tính duy nhất toàn cục. Trong thực tế ứng dụng, cách dễ áp dụng là tạo một ID có phần ngẫu nhiên đủ mạnh và phần domain do hệ thống kiểm soát.

Ví dụ:

```text
logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org
```

Giá trị này có thể được sử dụng trong:

```text
HTML:
  src="cid:logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org"

MIME:
  Content-ID: <logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org>
```

### Vì sao không dùng một CID cố định cho mọi email?

Ví dụ:

```java
private static final String LOGO_CID = "logo@example.org";
```

Hằng số này bảo đảm HTML và MIME part trong một lần gửi có thể dùng chung ID. Tuy nhiên, nếu áp dụng nguyên xi cho mọi email, giá trị Content-ID bị lặp giữa các message khác nhau, không đáp ứng yêu cầu uniqueness toàn cục của định dạng.

Một lựa chọn tốt hơn là **tạo CID mới cho từng message**, sau đó dùng lại đúng giá trị đó ở mọi nơi trong message ấy:

```java
String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";
```

Nếu cùng một logo được tham chiếu ở ba vị trí trong HTML, cả ba vị trí dùng cùng `logoCid`, và message chỉ cần một MIME part chứa logo.

### “Ổn định” không có nghĩa là phải cố định qua mọi email

Trong bài này, ổn định có nghĩa:

- Tạo ID đúng một lần cho mỗi inline resource trong message.
- Lưu giá trị đó trong mail model/context hoặc biến của quá trình dựng message.
- Dùng lại nguyên giá trị khi render HTML và gọi `addInline`.
- Không tạo lại ID độc lập ở hai tầng.

Với message tiếp theo, có thể tạo CID mới. Nếu nghiệp vụ cần tái tạo chính xác cùng một message qua retry, có thể dùng một notification ID duy nhất kết hợp với tên resource để tạo ID xác định. Khi đó phải bảo đảm notification ID là duy nhất theo phạm vi cần thiết và không đưa dữ liệu cá nhân hoặc bí mật vào CID.

## 3. Cấu trúc của Content-ID và CID URI

Trong MIME header, Content-ID được biểu diễn theo dạng message-id, thường có dấu ngoặc nhọn:

```text
Content-ID: <logo-550e8400@mail.example.org>
```

Trong HTML, tham chiếu CID bỏ dấu ngoặc nhọn và thêm scheme `cid:`:

```html
<img src="cid:logo-550e8400@mail.example.org" alt="Logo"/>
```

Với `MimeMessageHelper`, truyền giá trị Content-ID **không có dấu ngoặc nhọn và không có tiền tố `cid:`**. Helper tự tạo header MIME theo định dạng tương ứng.

Ví dụ:

```java
String contentId = "logo-550e8400@mail.example.org";

helper.addInline(
        contentId,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

Trong HTML:

```html
<img src="cid:logo-550e8400@mail.example.org" alt="Logo"/>
```

Không truyền:

```java
// Không thêm dấu ngoặc nhọn:
helper.addInline(
        "<logo-550e8400@mail.example.org>",
        resource,
        "image/png"
);

// Không thêm cid: vào đối số:
helper.addInline(
        "cid:logo-550e8400@mail.example.org",
        resource,
        "image/png"
);
```

Vì helper có thể tự bọc giá trị bằng dấu ngoặc nhọn, cách truyền sai có nguy cơ tạo header không đúng hoặc khiến CID trong HTML không khớp với MIME part.

### Dùng ký tự đơn giản

Nên tạo ID bằng các ký tự ASCII đơn giản, ví dụ:

- Chữ cái Latin.
- Chữ số.
- Dấu gạch ngang `-`.
- Dấu chấm `.`.
- Dấu `@` phân tách phần local và domain.

Tránh khoảng trắng, xuống dòng, dấu ngoặc nhọn, dấu nháy và ký tự điều khiển. CID URI có quy tắc escaping riêng khi chứa ký tự đặc biệt; dùng một token đơn giản giúp giảm rủi ro phải encode/decode phức tạp.

Không lấy CID trực tiếp từ tên file, tên khách hàng hoặc dữ liệu request. Tạo định danh ở backend bằng quy tắc do ứng dụng kiểm soát.

## 4. Quan hệ giữa CID và multipart/related

Hình inline thường nằm trong một MIME structure có dạng `multipart/related`. Một part chứa HTML, các part còn lại chứa ảnh mà HTML tham chiếu.

```text
MimeMessage
└── multipart/related
    ├── text/html; charset=UTF-8
    │     |
    │     +-- <img src="cid:logo-...@mail.example.org">
    │     +-- <img src="cid:banner-...@mail.example.org">
    │
    ├── image/png
    │     Content-ID: <logo-...@mail.example.org>
    │
    └── image/jpeg
          Content-ID: <banner-...@mail.example.org>
```

Mỗi ảnh có một MIME part và Content-ID riêng. HTML dùng CID URI để liên kết tới đúng part.

### Inline resource khác attachment thông thường

| Đặc điểm | Inline resource | Attachment |
| --- | --- | --- |
| Mục đích | Hiển thị trong nội dung HTML | Được người nhận mở/tải riêng |
| API Spring | `addInline(...)` | `addAttachment(...)` |
| Header disposition thường dùng | `inline` | `attachment` |
| HTML tham chiếu | `src="cid:..."` | Thường không cần |
| Content-ID | Cần để HTML tham chiếu | Có thể tồn tại nhưng không nhất thiết cần cho mục đích tải file |

Một ảnh có thể được gắn inline và hiển thị trong HTML; một PDF hóa đơn thường là attachment. Đừng dùng `addAttachment` rồi mong `cid:...` tự động tìm thấy ảnh. Hãy dùng API inline cho tài nguyên được HTML tham chiếu.

### Có cần tự tạo multipart/related header không?

Không. Khi dùng `MimeMessageHelper`, chọn chế độ multipart phù hợp và gọi `setText`/`addInline`. Helper cùng Jakarta Mail quản lý cấu trúc part và boundary.

Ví dụ với email HTML và ảnh inline:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        StandardCharsets.UTF_8.name()
);
```

Nếu email vừa có ảnh inline vừa có file đính kèm thông thường, dùng chế độ hỗ trợ mixed/related:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);
```

Chọn mode dựa trên cấu trúc nội dung cần gửi; không tự gán `Content-Type: multipart/related` bằng `setHeader`.

## 5. Tạo Content-ID một lần trong tầng dựng mail

Nguyên tắc triển khai quan trọng nhất là **tạo ID ở một nơi và truyền nó tới mọi nơi cần dùng**.

Không nên để template tự tạo một giá trị, rồi service gọi `addInline` lại tạo UUID khác. Template engine không nên tự quyết định danh tính MIME part.

Một luồng rõ ràng:

```text
Mail composer
    |
    | tạo logoCid một lần
    |
    +----------------------+
    |                      |
    v                      v
Template context       MimeMessageHelper
logoCid = value        addInline(value, resource)
    |                      |
    v                      v
src="cid:value"        Content-ID: <value>
    |                      |
    +----------+-----------+
               |
               v
       MIME message nhất quán
```

Ví dụ:

```java
String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";

context.setVariable("logoCid", logoCid);

String html = templateEngine.process(
        "mail/notification",
        context
);

helper.setText(plainText, html);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

Giá trị `logoCid` được tạo trước khi render, sau đó được dùng lại khi gắn resource. Cách làm này bảo đảm chuỗi trong HTML và MIME part khớp nhau.

### Vì sao nên tạo CID trước khi render template?

Template cần biết giá trị để tạo `src="cid:..."`. Nếu chỉ tạo CID sau khi HTML đã render, ứng dụng phải sửa chuỗi HTML hoặc render lại. Cả hai cách đều làm luồng phức tạp hơn và dễ sai.

Hãy coi CID là một phần của **mail model nội bộ**: renderer nhận ID đã được cấp, template chỉ sử dụng nó; mail composer dùng cùng ID để tạo inline part.

## 6. Ví dụ Spring Boot + Thymeleaf + MimeMessageHelper

Ví dụ này gửi email thông báo HTML có logo inline. CID được tạo một lần trong service và truyền cho cả template lẫn helper.

### 6.1. Cấu trúc tài nguyên

```text
src/main/resources/
├── templates/
│   └── mail/
│       └── notification.html
└── mail/
    └── logo.png
```

`notification.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <header>
    <img th:src="'cid:' + ${logoCid}"
         alt="Logo công ty"
         width="120"
         height="40"/>
  </header>

  <h1 th:text="${title}">Thông báo</h1>
  <p>Xin chào <span th:text="${customerName}">Khách hàng</span>.</p>
  <p th:text="${message}">Nội dung thông báo.</p>
</body>
</html>
```

Thymeleaf nhận `logoCid` như một giá trị dữ liệu. Biểu thức `th:src` tạo URL CID từ tiền tố cố định `cid:` và giá trị do backend cung cấp. Các trường văn bản dùng `th:text` để HTML-escape dữ liệu.

### 6.2. Cấu hình SMTP

Ví dụ `application.yml` với máy chủ SMTP submission hỗ trợ STARTTLS:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

Các placeholder được cấp từ môi trường hoặc nguồn cấu hình bảo mật. Cổng 587/STARTTLS chỉ là ví dụ; host, TLS và phương thức xác thực phải phù hợp với SMTP provider thật.

### 6.3. Service tạo một CID và dùng lại

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.UUID;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final String fromAddress;

    public NotificationMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
        this.fromAddress = fromAddress;
    }

    public void sendNotification(
            String recipient,
            String customerName,
            String title,
            String body
    ) throws MessagingException {

        // Tạo CID đúng một lần cho inline image của message này.
        String logoCid = "logo-" + UUID.randomUUID()
                + "@mail.example.org";

        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("logoCid", logoCid);
        context.setVariable("customerName", customerName);
        context.setVariable("title", title);
        context.setVariable("message", body);

        String html = templateEngine.process(
                "mail/notification",
                context
        );

        String plain = "Xin chào " + customerName + ".\n"
                + title + "\n"
                + body;

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject(title);

        // Đặt body trước, rồi gắn inline resource.
        helper.setText(plain, html);
        helper.addInline(
                logoCid,
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        mailSender.send(message);
    }
}
```

Trong ví dụ:

1. `logoCid` được tạo một lần bằng UUID và domain do ứng dụng kiểm soát.
2. Cùng giá trị được đặt vào `Context` trước khi render template.
3. HTML sinh ra tham chiếu `cid:` cộng với giá trị đó.
4. `helper.addInline(...)` nhận đúng giá trị CID, resource và media type `image/png`.
5. Helper được tạo ở chế độ `MULTIPART_MODE_RELATED` vì email có HTML và inline image.
6. `setText(...)` được gọi trước `addInline(...)`, theo cách sử dụng được khuyến nghị cho inline resource.

`customerName`, `title` và `body` trong ví dụ cần được kiểm tra theo nghiệp vụ. Template dùng `th:text` để hiển thị chúng như văn bản. Tên miền `mail.example.org` chỉ là miền minh họa; khi triển khai nên dùng miền do tổ chức kiểm soát.

## 7. Nhiều inline resource trong cùng một message

Nếu email có logo, banner và biểu tượng trạng thái, mỗi resource cần một CID riêng:

```text
HTML:
  <img src="cid:logo-...@mail.example.org">
  <img src="cid:banner-...@mail.example.org">
  <img src="cid:status-...@mail.example.org">

MIME parts:
  Content-ID: <logo-...@mail.example.org>
  Content-ID: <banner-...@mail.example.org>
  Content-ID: <status-...@mail.example.org>
```

Ví dụ Java:

```java
String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";
String bannerCid = "banner-" + UUID.randomUUID()
        + "@mail.example.org";
String statusCid = "status-" + UUID.randomUUID()
        + "@mail.example.org";

context.setVariable("logoCid", logoCid);
context.setVariable("bannerCid", bannerCid);
context.setVariable("statusCid", statusCid);

String html = templateEngine.process("mail/summary", context);

helper.setText(plainText, html);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addInline(
        bannerCid,
        new ClassPathResource("mail/banner.jpg"),
        "image/jpeg"
);
helper.addInline(
        statusCid,
        new ClassPathResource("mail/status-check.png"),
        "image/png"
);
```

Mỗi CID được sinh độc lập. Không dùng chung một ID cho ba ảnh khác nhau.

### Một resource được tham chiếu nhiều lần

Nếu logo xuất hiện ở header và footer, cả hai thẻ HTML có thể dùng cùng một CID:

```html
<header>
  <img src="cid:logo-123@mail.example.org" alt="Logo"/>
</header>

<footer>
  <img src="cid:logo-123@mail.example.org" alt="Logo"/>
</footer>
```

Chỉ cần một MIME part có Content-ID tương ứng. Điều này tránh tạo các part trùng nội dung không cần thiết.

Quy tắc:

- **Cùng một tài nguyên, nhiều vị trí hiển thị:** dùng cùng CID.
- **Các tài nguyên khác nhau:** dùng CID riêng.
- **Mỗi message mới:** tạo bộ CID mới theo phạm vi uniqueness đã chọn.

## 8. Tổ chức CID thành một mail model

Khi template có nhiều inline image, không nên rải việc tạo UUID ở nhiều method. Có thể tạo một model đại diện cho các tài nguyên inline:

```java
import java.util.UUID;

public record InlineContentIds(
        String logo,
        String banner,
        String status
) {
    public static InlineContentIds create() {
        return new InlineContentIds(
                createId("logo"),
                createId("banner"),
                createId("status")
        );
    }

    private static String createId(String name) {
        return name + "-" + UUID.randomUUID()
                + "@mail.example.org";
    }
}
```

Khi dựng message:

```java
InlineContentIds ids = InlineContentIds.create();

context.setVariable("logoCid", ids.logo());
context.setVariable("bannerCid", ids.banner());
context.setVariable("statusCid", ids.status());

String html = templateEngine.process("mail/summary", context);
helper.setText(plainText, html);

helper.addInline(
        ids.logo(),
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addInline(
        ids.banner(),
        new ClassPathResource("mail/banner.jpg"),
        "image/jpeg"
);
helper.addInline(
        ids.status(),
        new ClassPathResource("mail/status-check.png"),
        "image/png"
);
```

`InlineContentIds` đóng vai trò nơi quản lý ID. Khi thêm một ảnh mới vào template, model này được mở rộng cùng phần gắn resource. Việc đó giúp tránh tình trạng template tham chiếu CID nhưng composer quên thêm part tương ứng.

### Có nên dùng Map?

Có thể dùng Map khi số lượng resource thay đổi theo template:

```java
Map<String, String> contentIds = new LinkedHashMap<>();
contentIds.put(
        "logo",
        "logo-" + UUID.randomUUID() + "@mail.example.org"
);
contentIds.put(
        "banner",
        "banner-" + UUID.randomUUID() + "@mail.example.org"
);
```

Nhưng Map nên được tạo ở một tầng duy nhất và truyền nguyên giá trị tới renderer/composer. Đừng để template tự suy ra CID từ tên file trong khi code Java dùng một quy tắc khác.

## 9. Tạo CID xác định để hỗ trợ retry và replay

Tạo UUID ngẫu nhiên cho mỗi message là cách đơn giản và phù hợp với phần lớn email. Nhưng một số hệ thống muốn **render lại cùng một notification với cùng CID**, ví dụ để đối chiếu kết quả hoặc tái tạo message từ event đã lưu.

Khi đó, có thể tạo CID xác định từ:

- Một `notificationId` duy nhất do backend cấp.
- Một khóa tài nguyên ổn định như `logo`, `banner` hoặc `invoice-stamp`.
- Một domain do ứng dụng kiểm soát.

Ví dụ:

```java
String logoCid = "logo-" + notificationId
        + "@mail.example.org";
```

Điều kiện để cách này an toàn:

1. `notificationId` có uniqueness đủ mạnh trên phạm vi các message được phát hành.
2. Một notification có thể có nhiều resource, nên mỗi resource có key khác nhau.
3. Không tái sử dụng notification ID cho hai message độc lập nếu muốn Content-ID toàn cục không bị trùng.
4. Không dùng thông tin cá nhân hoặc token bí mật làm thành phần CID.
5. ID được tạo từ dữ liệu có định dạng giới hạn, không chứa ký tự điều khiển.

Nếu notification ID là UUID, kết quả có thể là:

```text
logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org
banner-550e8400-e29b-41d4-a716-446655440000@mail.example.org
```

Hai resource có ID khác nhau vì phần key khác nhau. Nếu notification được retry bằng cùng ID, CID được tái tạo giống nhau.

### Chọn UUID ngẫu nhiên hay ID xác định?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Mỗi lần gửi là một message mới, không cần tái tạo CID | UUID ngẫu nhiên một lần cho mỗi message |
| Retry phải tái tạo cùng cấu trúc MIME có CID ổn định | Notification ID duy nhất + resource key |
| Nhiều vị trí HTML tham chiếu cùng ảnh | Dùng chung CID của ảnh trong message |
| Nhiều ảnh khác nhau trong cùng message | Mỗi ảnh một CID |
| Muốn dùng một CID cố định cho tất cả email | Không phù hợp với yêu cầu uniqueness toàn cục |

Lưu ý: CID ổn định không làm cho việc gửi email trở thành idempotent. Chống gửi trùng cần notification state/idempotency key và chính sách retry ở tầng nghiệp vụ. Content-ID chỉ định danh MIME part.

## 10. Tạo CID không phụ thuộc tên file

Tên file và Content-ID có mục đích khác nhau:

```text
Filename:
  logo-company.png

Content-ID:
  logo-550e8400-e29b-41d4-a716-446655440000@mail.example.org
```

Tên file giúp nhận diện tài nguyên hoặc cung cấp tên hiển thị. Content-ID là khóa liên kết giữa HTML và MIME part. Không bắt buộc chúng giống nhau.

Ví dụ:

```java
String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";

helper.addInline(
        logoCid,
        new ClassPathResource("mail/brand-mark.png"),
        "image/png"
);
```

Trong HTML, tham chiếu `cid:` cộng với `logoCid`. Tên file vật lý `brand-mark.png` không cần xuất hiện trong CID.

### Không lấy filename làm CID

Không nên:

```java
String contentId = file.getName();
helper.addInline(contentId, file);
```

Hai email hoặc hai resource có thể cùng tên `logo.png`; tên file cũng có thể chứa dấu cách, Unicode hoặc ký tự cần escaping. Dùng filename làm CID làm tăng nguy cơ va chạm và khiến hai khái niệm bị trộn lẫn.

## 11. Kiểm tra tính nhất quán giữa HTML và MIME part

Một message hợp lệ về mặt liên kết CID cần thỏa các điều kiện:

1. Mọi CID được tham chiếu trong HTML có một MIME part tương ứng.
2. Mỗi MIME part được tham chiếu có Content-ID khớp với CID URI sau khi áp dụng quy tắc URI.
3. Mỗi resource khác nhau có một Content-ID riêng.
4. Resource có `Content-Type` đúng, ví dụ `image/png` hoặc `image/jpeg`.
5. Part được đặt ở cấu trúc MIME liên quan phù hợp, thường là `multipart/related`.
6. Byte nguồn có thể đọc được trong suốt quá trình serialize message.

Ví dụ message có hai ảnh:

```text
HTML references:
  cid:logo-a1@mail.example.org
  cid:banner-b2@mail.example.org

Inline MIME parts:
  Content-ID: <logo-a1@mail.example.org>
  Content-Type: image/png

  Content-ID: <banner-b2@mail.example.org>
  Content-Type: image/jpeg
```

Ví dụ lỗi:

```text
HTML:
  <img src="cid:logo-a1@mail.example.org">

MIME:
  Content-ID: <logo-b2@mail.example.org>
```

HTML tìm `logo-a1`, nhưng message chỉ có part `logo-b2`. Mail client không thể tìm thấy ảnh theo tham chiếu đó.

### Tham chiếu tới CID không tồn tại

Nếu template chứa:

```html
<img src="cid:bannerCid" alt="Banner"/>
```

nhưng composer không gọi `addInline` cho CID đó, ảnh sẽ bị thiếu. Để giảm lỗi, hãy quản lý danh sách inline resources bằng một model chung và tạo template context từ chính model đó.

### MIME part tồn tại nhưng không được HTML tham chiếu

Điều ngược lại cũng có thể xảy ra: composer thêm logo nhưng template không dùng CID. Part vẫn nằm trong message, làm tăng dung lượng mà không có tác dụng trình bày. Nên giữ danh sách resource cần thiết theo template và tránh thêm ảnh không dùng.

## 12. Thứ tự gọi trong MimeMessageHelper

Khi dùng inline resource, thứ tự phổ biến được Spring khuyến nghị là:

1. Tạo `MimeMessage`.
2. Tạo `MimeMessageHelper` ở chế độ multipart phù hợp.
3. Thiết lập From, To, Subject.
4. Render hoặc chuẩn bị nội dung HTML.
5. Gọi `setText(...)` để thiết lập body.
6. Gọi `addInline(...)` cho từng resource.
7. Gọi `JavaMailSender.send(...)`.

Ví dụ:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setFrom(fromAddress);
helper.setTo(recipient);
helper.setSubject(subject);

String logoCid = createLogoCid();
context.setVariable("logoCid", logoCid);
String html = templateEngine.process("mail/notification", context);

helper.setText(plainText, html);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

mailSender.send(message);
```

Lệnh `setText` đặt body để helper có thể xây dựng cấu trúc liên quan; sau đó `addInline` thêm part mà body tham chiếu. Nếu thêm inline resource trước rồi gọi `setText` sau, một số cấu trúc multipart có thể bị tổ chức lại và làm ảnh không hiển thị như mong đợi.

**Đừng tự sửa boundary hoặc top-level Content-Type** sau khi helper tạo cấu trúc. Boundary và các header part do Jakarta Mail quản lý.

## 13. Email có cả inline resource và attachment

Một email có thể chứa:

- HTML body.
- Logo inline được tham chiếu bằng CID.
- PDF attachment để người nhận tải về.

Sơ đồ:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── text/html; charset=UTF-8
    │   │     └── <img src="cid:logo-...">
    │   └── image/png
    │         └── Content-ID: <logo-...>
    └── application/pdf
          └── Content-Disposition: attachment
```

Ví dụ:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);

String logoCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";
context.setVariable("logoCid", logoCid);

String html = templateEngine.process("mail/invoice", context);

helper.setFrom(fromAddress);
helper.setTo(recipient);
helper.setSubject("Hóa đơn của bạn");
helper.setText(
        "Hóa đơn được đính kèm trong email.",
        html
);

helper.addInline(
        logoCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

mailSender.send(message);
```

Ở đây:

- CID chỉ áp dụng cho logo inline.
- PDF được thêm bằng `addAttachment`, không cần HTML CID.
- `MULTIPART_MODE_MIXED_RELATED` hỗ trợ cấu trúc có related content và attachment.
- `setText(plain, html)` cung cấp cả phiên bản text thuần và HTML.
- `logoCid` được truyền cùng một giá trị cho template và helper.

## 14. Xử lý nhiều lần render và retry

Một hệ thống gửi email bất đồng bộ có thể render ở worker và retry khi SMTP tạm thời không sẵn sàng. Cần quyết định CID được tạo ở thời điểm nào.

### Tạo CID mỗi lần thử gửi

Nếu mỗi lần retry tạo một `MimeMessage` mới và sinh UUID mới, HTML và MIME part trong lần thử đó vẫn khớp nhau. Đây là cách đơn giản khi CID không được dùng làm định danh nghiệp vụ và không cần so sánh raw message giữa các lần thử.

### Giữ CID theo notification

Nếu cần tái tạo cùng một message, có thể tạo CID từ notification ID và asset key. Khi retry, cùng notification sẽ tạo lại cùng CID. Điều kiện là:

- Notification ID không bị tái sử dụng cho message khác.
- Asset key phân biệt các resource.
- Template version và danh sách inline resource cũng được giữ nhất quán nếu cần replay chính xác.

### Không chia sẻ mutable CID map giữa các message

Ví dụ sai:

```java
// Không nên: map dùng chung cho mọi lần gửi và bị thay đổi.
private final Map<String, String> contentIds = new HashMap<>();
```

Nếu hai email được dựng đồng thời và cùng sửa map, template của email này có thể nhận CID của email kia hoặc resource bị ánh xạ sai. Hãy tạo CID map riêng cho từng message hoặc từng request render.

### Không dùng CID để chống gửi trùng

Hai lần gửi cùng notification có cùng CID không ngăn SMTP nhận hai message. Ngược lại, hai lần gửi có CID khác nhau cũng không có nghĩa đó là hai nghiệp vụ khác nhau. Dùng `notificationId`, trạng thái gửi và idempotency policy ở tầng ứng dụng để quản lý retry.

## 15. Những lỗi thường gặp khi tạo Content-ID

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Logo không hiển thị | CID trong HTML khác Content-ID MIME part | Tạo một biến CID và dùng lại ở cả hai nơi |
| Một ảnh hiển thị thay cho ảnh khác | Hai resource dùng cùng Content-ID | Tạo CID riêng cho từng resource |
| Template tham chiếu `cid:logo`, helper nhận `logo.png` | Nhầm CID với filename | Dùng một token CID riêng, không lấy tên file làm CID |
| Header có dấu ngoặc nhọn kép | Truyền `<...>` vào `addInline` trong khi helper tự bọc | Truyền Content-ID dạng trần |
| HTML chứa `cid:cid:...` | Đối số đã có tiền tố `cid:` rồi template thêm lần nữa | Helper nhận ID thuần; HTML thêm đúng một `cid:` |
| Resource được thêm nhưng không được tham chiếu | Template dùng CID khác hoặc không dùng ảnh | Đồng bộ danh sách model/template/composer |
| CID ổn định trong template nhưng sai ở message | Template và helper tự sinh ID riêng | Sinh một lần trong mail composer |
| Ảnh bị gửi như file attachment | Dùng `addAttachment` thay vì `addInline` | Dùng `addInline` và cấu trúc related |
| CID cố định bị lặp giữa các email | Dùng hằng số toàn ứng dụng cho mọi message | Dùng UUID hoặc notification ID duy nhất |
| Ảnh không hiển thị trong một số client | MIME mode, CID hoặc hỗ trợ client khác nhau | Kiểm tra raw MIME và thử client mục tiêu |
| Email tăng dung lượng không cần thiết | Thêm cùng ảnh thành nhiều MIME part | Tái sử dụng một CID cho cùng resource |
| Resource không đọc được khi gửi | Nguồn stream one-shot hoặc file đã bị xóa | Dùng Resource có thể mở lại và giữ vòng đời nguồn |
| Link ảnh ngoài bị chặn | Client chặn tải external image | Dùng inline resource khi phù hợp, hoặc chấp nhận chính sách tải ảnh của client |

### Lỗi 1: tạo CID hai lần

```java
context.setVariable(
        "logoCid",
        "logo-" + UUID.randomUUID() + "@mail.example.org"
);

String html = templateEngine.process("mail/notification", context);

// Sai: tạo một UUID khác cho MIME part.
String mimeCid = "logo-" + UUID.randomUUID()
        + "@mail.example.org";

helper.setText(html, true);
helper.addInline(
        mimeCid,
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

Hai UUID khác nhau khiến HTML không tìm thấy MIME part. Hãy tạo một biến `logoCid` duy nhất, truyền nó vào context và `addInline`.

### Lỗi 2: dùng cùng CID cho nhiều ảnh

```java
helper.addInline(
        "image@mail.example.org",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addInline(
        "image@mail.example.org",
        new ClassPathResource("mail/banner.jpg"),
        "image/jpeg"
);
```

Hai MIME part cạnh tranh cùng một định danh. Hãy cấp `logo-...` và `banner-...` riêng biệt.

### Lỗi 3: truyền `cid:` vào helper

```java
// Sai cách truyền:
helper.addInline(
        "cid:logo-123@mail.example.org",
        resource,
        "image/png"
);
```

Helper nhận Content-ID, còn `cid:` là scheme trong HTML. Sửa:

```java
String logoCid = "logo-123@mail.example.org";
helper.addInline(logoCid, resource, "image/png");

// HTML:
String src = "cid:" + logoCid;
```

### Lỗi 4: dùng filename làm CID

```java
helper.addInline("logo.png", resource, "image/png");
```

Về mặt chuỗi, một số thư viện/client có thể xử lý giá trị này, nhưng nó không tạo được quy ước uniqueness tốt. Tên file có thể lặp hoặc thay đổi. Dùng một ID độc lập và có namespace.

### Lỗi 5: gọi `addInline` trước `setText`

Nếu helper phải tái cấu trúc multipart khi thiết lập body sau đó, part inline có thể không còn ở vị trí mà HTML tham chiếu mong đợi. Theo cách dùng thông thường, thiết lập text/HTML trước, rồi thêm inline resource.

## 16. Kiểm tra raw MIME khi ảnh không hiển thị

Khi email tới mailbox nhưng logo bị thiếu, hãy xem **Show original / View source** hoặc công cụ xem raw message của hệ thống nhận.

Một cấu trúc mong đợi:

```text
Content-Type: multipart/related; boundary="rel-123"

--rel-123
Content-Type: text/html; charset=UTF-8

<html>
  <body>
    <img src="cid:logo-123@mail.example.org" alt="Logo">
  </body>
</html>

--rel-123
Content-Type: image/png
Content-ID: <logo-123@mail.example.org>
Content-Disposition: inline
Content-Transfer-Encoding: base64

iVBORw0KGgo...

--rel-123--
```

Chuỗi base64 ở trên chỉ là đoạn đầu minh họa, không phải ảnh hoàn chỉnh.

Các bước quan sát:

1. Kiểm tra top-level MIME structure có related part phù hợp hay không.
2. Tìm HTML part và đọc giá trị `src="cid:..."`.
3. Tìm MIME part có `Content-ID` tương ứng.
4. Kiểm tra `Content-Type` của ảnh có khớp định dạng thật không.
5. Kiểm tra `Content-Disposition` và byte transfer encoding.
6. Nếu CID khớp nhưng ảnh vẫn không hiện, kiểm tra byte resource, MIME nesting và hành vi của mail client.

Đừng chỉ nhìn header ngoài cùng. Nếu message là `multipart/mixed`, phần related có thể nằm trong một MIME part con.

### Kiểm tra trong code trước khi gửi

Có thể tổ chức dữ liệu để không thể tạo template mà thiếu ID resource:

```java
public record InlineAsset(
        String contentId,
        Resource resource,
        String contentType
) {}
```

Một `InlineAsset` giữ chung ba thông tin: ID, nguồn byte và media type. Renderer lấy `contentId` từ danh sách asset để đưa vào context; composer dùng chính danh sách đó để gọi `addInline`. Cách này giảm nguy cơ template và MIME part được cấu hình độc lập.

## 17. Content-ID và quyền riêng tư

Content-ID thường xuất hiện trong raw MIME và có thể được nhìn thấy khi người nhận xem nguồn thư. Vì vậy:

- Không dùng email address hoặc tên người dùng làm CID nếu không cần thiết.
- Không nhúng access token, reset token hoặc dữ liệu cá nhân vào CID.
- Không xem CID như một cơ chế bảo mật hoặc quyền truy cập.
- Dùng một định danh ngẫu nhiên hoặc mã kỹ thuật không nhạy cảm.
- Tránh để CID chứa thông tin nội bộ như đường dẫn filesystem hoặc tên bucket.

CID chỉ là cách định danh MIME part. Người nhận không cần biết ID đó có liên quan đến notification nào trong database.

### CID không phải URL bảo vệ ảnh

Ảnh inline được mang bên trong message. Người nhận không cần gọi một endpoint công khai để tải ảnh bằng CID. Tuy nhiên, nếu email còn có ảnh ngoài qua URL HTTPS, ảnh đó có thể được mail client tải từ server và tạo ra request có thông tin thời điểm truy cập. Hai cơ chế này có đặc điểm riêng:

| Cơ chế | Dữ liệu ảnh ở đâu? | Khi nào được lấy? |
| --- | --- | --- |
| CID inline | Nằm trong MIME message | Đã được gửi kèm email |
| URL HTTPS | Trên máy chủ web/CDN | Khi mail client tải URL, có thể bị chặn/proxy/cache |

Chọn cơ chế dựa trên dung lượng, trải nghiệm, quyền riêng tư và khả năng tương thích. Content-ID không mã hóa hay bảo vệ nội dung ảnh khỏi người nhận email.

## 18. Tương thích với các mail client

CID inline được nhiều mail client hỗ trợ, nhưng cách hiển thị còn phụ thuộc:

- Cấu trúc `multipart/related` và vị trí của HTML part.
- Content-ID trong HTML có khớp header MIME không.
- `Content-Type` và byte ảnh có đúng định dạng không.
- Kích thước ảnh và cách client xử lý inline image.
- Quy tắc lọc nội dung và chính sách bảo mật của client.
- CSS/layout của HTML email.

Không nên thiết kế email sao cho ảnh inline là nguồn duy nhất chứa thông tin quan trọng. Luôn có `alt` text có nghĩa và nội dung chính ở dạng văn bản. Ví dụ:

```html
<img src="cid:logo-123@mail.example.org"
     alt="Tên công ty"
     width="120"
     height="40"/>
```

Nếu logo không hiển thị, người đọc vẫn có thể nhận biết nội dung từ `alt` và phần văn bản khác.

### Có thể dùng cùng một ảnh vừa CID vừa attachment không?

Có thể tạo hai MIME part hoặc tổ chức nội dung theo mục đích riêng, nhưng thường không cần thiết. Nếu cùng một tài nguyên cần hiển thị trong body và cho phép tải riêng, hãy cân nhắc liệu một inline part có đủ cho trải nghiệm client hay không. Đừng giả định `addInline` tự tạo thêm một attachment độc lập.

Nếu yêu cầu tải file là quan trọng, thêm một attachment có tên rõ ràng bằng `addAttachment`, đồng thời giữ inline part phục vụ hiển thị. Cách này có thể làm message lớn hơn vì dữ liệu được lặp lại.

## 19. Quy tắc thiết kế cho Content-ID

| Quy tắc | Thực hiện |
| --- | --- |
| Sinh ID | Tạo một lần ở mail composer cho từng inline resource |
| Phạm vi | Unique toàn cục theo quy tắc Content-ID; dùng UUID hoặc notification ID duy nhất |
| Cùng resource nhiều vị trí | Dùng cùng một CID trong mọi HTML reference |
| Resource khác nhau | Cấp CID riêng |
| Đối số `addInline` | Truyền ID trần, không `cid:` và không dấu ngoặc nhọn |
| HTML reference | Dùng `src="cid:" + contentId` |
| Media type | Chỉ định rõ khi biết định dạng, ví dụ `image/png` |
| MIME mode | Chọn `MULTIPART_MODE_RELATED` hoặc `MULTIPART_MODE_MIXED_RELATED` phù hợp |
| Thứ tự | Thiết lập body bằng `setText` trước khi gọi `addInline` |
| Dữ liệu CID | Chỉ dùng ký tự đơn giản do backend tạo |
| Retry/replay | Chọn UUID mỗi attempt hoặc ID xác định theo notification theo yêu cầu |
| Bảo mật | Không nhúng token, PII hoặc secret vào Content-ID |
| Kiểm tra | Đối chiếu CID URI trong HTML với Content-ID của từng MIME part |

## 20. Tình huống tự luyện

### Tình huống A: cùng logo xuất hiện ở header và footer

Template có hai thẻ `<img>` dùng cùng hình logo.

**Cách xử lý:** tạo một `logoCid`, dùng nó cho cả hai `src="cid:..."` và chỉ thêm một MIME part với `addInline(logoCid, ...)`.

### Tình huống B: email có logo và banner khác nhau

**Cách xử lý:** tạo `logoCid` và `bannerCid` riêng; đưa cả hai vào context; gọi `addInline` hai lần với đúng CID tương ứng.

### Tình huống C: logo không hiển thị dù `addInline` đã chạy

**Cách xử lý:** xem raw MIME, đối chiếu `src` trong HTML với `Content-ID` của part. Nếu khớp, kiểm tra MIME nesting, media type và byte resource.

### Tình huống D: retry cùng notification

Hệ thống muốn replay đúng cùng model và template.

**Cách xử lý:** nếu cần CID xác định, tạo ID từ notification ID duy nhất và resource key. Giữ version template, asset mapping và dữ liệu cần thiết theo chính sách lưu trữ. Việc này không thay thế idempotency của gửi email.

### Tình huống E: hai email gửi đồng thời dùng chung template

**Cách xử lý:** template có thể dùng chung, nhưng CID map và context phải riêng theo từng message. Không lưu CID đang dùng trong một biến mutable singleton.

### Tình huống F: template có `cid:logo` cố định

**Cách xử lý:** nếu chỉ xét một message, giá trị có thể liên kết được; nhưng dùng hằng số giống nhau trên mọi message không đáp ứng uniqueness toàn cục. Tạo CID theo message và truyền vào template.

## 21. Kết luận

Content-ID là cầu nối giữa một vị trí `cid:` trong HTML và MIME part chứa inline resource. Để ảnh hiển thị đúng, **giá trị phải được tạo một lần và dùng nhất quán ở cả template lẫn `MimeMessageHelper.addInline(...)`**. Mỗi tài nguyên khác nhau cần ID riêng; cùng một ảnh được tham chiếu nhiều lần có thể dùng chung ID. Nên tạo CID mới theo từng message bằng UUID hoặc một notification ID duy nhất kết hợp với asset key, đồng thời dùng domain do ứng dụng kiểm soát.

Trong Spring Framework Mail, hãy chọn chế độ multipart phù hợp, render HTML với CID đã được truyền vào context, gọi `setText(...)` trước `addInline(...)`, rồi để Jakarta Mail tạo header và boundary. Kiểm tra raw MIME khi ảnh không hiển thị sẽ giúp xác định lỗi nằm ở CID mapping, MIME structure, media type hay byte của resource.
