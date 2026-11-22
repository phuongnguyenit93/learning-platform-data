# Bản địa hóa subject và nội dung email

Một email được gửi tới người dùng ở Việt Nam, Nhật Bản hay Pháp thường cần nhiều hơn việc dịch một câu sang ngôn ngữ khác. **Subject**, nội dung văn bản thuần, HTML, ngày giờ, số tiền, liên kết hỗ trợ và cách trình bày đều phải phù hợp với ngôn ngữ và vùng của người nhận. Trong **Spring Framework Mail**, có thể kết hợp `MessageSource`, resource bundle, template engine và `MimeMessageHelper` để tạo email đúng locale trước khi gửi qua `JavaMailSender`.

Bản địa hóa (*localization*, thường viết tắt là l10n) là quá trình điều chỉnh nội dung và cách biểu diễn cho một locale cụ thể. Nó bao gồm bản dịch, định dạng ngày/số/tiền tệ, múi giờ, liên kết theo vùng, quy tắc hiển thị từ phải sang trái và những yêu cầu nội dung tại thị trường đích.

Bài học này trình bày cách chọn locale cho email, tổ chức message bundle và HTML template, bản địa hóa subject cùng plain text/HTML, định dạng dữ liệu theo locale, xử lý fallback, truyền locale qua tác vụ bất đồng bộ và kiểm thử các phiên bản ngôn ngữ.

## 1. Vì sao phải bản địa hóa cả subject lẫn body?

Người nhận thường nhìn thấy **subject trước khi mở email**. Nếu subject bằng ngôn ngữ khác body, người dùng có thể hiểu nhầm nội dung hoặc bỏ qua thư. Tương tự, nếu HTML đã dịch nhưng plain text vẫn giữ tiếng Anh, người dùng đọc bằng client chỉ hỗ trợ văn bản sẽ nhận một trải nghiệm không nhất quán.

Ví dụ cùng một email xác nhận đơn hàng:

| Thành phần | `vi-VN` | `en-US` |
|---|---|---|
| Subject | Xác nhận đơn hàng ORD-1024 | Order confirmation ORD-1024 |
| Heading | Đơn hàng của bạn đã được xác nhận | Your order is confirmed |
| CTA | Theo dõi đơn hàng | Track your order |
| Footer | Cần hỗ trợ? Liên hệ chúng tôi. | Need help? Contact us. |
| Ngày | 12/11/2026 (theo quy ước vùng) | Nov 12, 2026 |
| Số tiền | 1.250.000 ₫ | $1,250.00 (nếu giao dịch thực sự bằng USD) |

Các ví dụ ngày và số tiền chỉ minh họa định dạng; giá trị thực cần dựa trên dữ liệu giao dịch và chính sách sản phẩm.

Bản địa hóa đồng bộ giúp người nhận nhận biết mục đích email từ subject, subject/plain/HTML truyền đạt cùng trạng thái nghiệp vụ, ngày và số phù hợp với vùng, và nội dung có thể được tái hiện theo locale đã chọn khi điều tra sự cố.

**Không nên dịch từng chuỗi rời rạc bằng cách nối các mảnh câu.** Trật tự từ, ngữ pháp, số nhiều và dấu câu khác nhau giữa các ngôn ngữ. Hãy dịch cả thông điệp hoặc dùng message pattern có tham số.

## 2. Phân biệt Locale, language, country, time zone và currency

Java biểu diễn locale bằng lớp `java.util.Locale`. Locale mô tả ngôn ngữ và có thể kèm vùng hoặc biến thể:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale usEnglish = Locale.forLanguageTag("en-US");
Locale britishEnglish = Locale.forLanguageTag("en-GB");
Locale japanese = Locale.forLanguageTag("ja-JP");
```

Một locale có thể biểu diễn bằng language tag theo chuẩn BCP 47:

```text
vi-VN
en-US
en-GB
ja-JP
fr-FR
ar-SA
```

Các khái niệm liên quan cần được tách riêng:

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Language | `vi`, `en`, `ja` | Ngôn ngữ dùng để chọn bản dịch. |
| Region | `VN`, `US`, `GB`, `JP` | Quy ước vùng, chính tả và định dạng. |
| Locale | `vi-VN`, `en-US` | Kết hợp ngôn ngữ và vùng. |
| Time zone | `Asia/Ho_Chi_Minh`, `America/New_York` | Xác định thời điểm địa phương. |
| Currency | `VND`, `USD`, `JPY` | Đơn vị tiền của giao dịch. |
| Measurement system | metric, US customary | Cách hiển thị đơn vị đo. |

**Locale không tự xác định tất cả thông tin cá nhân.** Người dùng có thể chọn giao diện tiếng Anh nhưng sống ở Việt Nam, dùng múi giờ Việt Nam và thanh toán bằng VND. Không nên suy luận currency hoặc time zone chỉ từ locale.

### Tạo Locale từ language tag

Ưu tiên `Locale.forLanguageTag(...)` khi dữ liệu đến từ cấu hình, profile hoặc HTTP header:

```java
Locale locale = Locale.forLanguageTag("vi-VN");

String language = locale.getLanguage(); // vi
String region = locale.getCountry();    // VN
String tag = locale.toLanguageTag();    // vi-VN
```

Không nên truyền chuỗi có dấu gạch dưới như `vi_VN` vào `forLanguageTag` như thể đó là language tag. Nếu hệ thống cũ lưu `vi_VN`, hãy chuyển đổi theo quy ước dữ liệu đã xác định hoặc chuẩn hóa sang BCP 47 trước khi dùng.

### Locale không phải múi giờ

Nếu email nói “Cuộc hẹn lúc 9:00”, người nhận cần biết đó là 9:00 ở múi giờ nào. `Locale` không đủ để xác định điều này. Hãy lấy `ZoneId` từ hồ sơ người dùng, cấu hình nghiệp vụ hoặc lịch sự kiện.

Tương tự, locale `en-US` không có nghĩa mọi số tiền đều phải hiển thị USD. **Tiền tệ phải lấy từ giao dịch**, còn locale chỉ quyết định cách trình bày số tiền đó.

## 3. Quyết định locale nào được dùng cho email

Locale của email cần được chọn bằng một chính sách rõ ràng. Những nguồn có thể dùng:

1. **Ngôn ngữ người dùng đã chọn trong hồ sơ:** thường là nguồn ưu tiên cho email tài khoản.
2. **Ngôn ngữ của giao dịch hoặc thị trường:** có thể phù hợp với hóa đơn, xác nhận mua hàng hoặc email pháp lý.
3. **Locale từ yêu cầu HTTP:** `Accept-Language` có thể giúp chọn ngôn ngữ khi người dùng chưa có preference.
4. **Locale mặc định của ứng dụng:** dùng khi không có nguồn phù hợp.
5. **Locale mặc định của template:** fallback cuối cùng nếu sản phẩm đã quy định.

Ví dụ chính sách:

```text
User profile locale
       |
       | không có
       v
Business transaction locale
       |
       | không có
       v
Request Accept-Language
       |
       | không có / không hỗ trợ
       v
Application default locale
```

Thứ tự trên chỉ là một chính sách mẫu. Với email hóa đơn, luật áp dụng hoặc nội dung liên quan hợp đồng, locale có thể phải theo thị trường của giao dịch. Với email tài khoản, lựa chọn của người dùng thường phù hợp hơn.

### Không dùng locale mặc định của máy chủ làm chính sách sản phẩm

`Locale.getDefault()` phụ thuộc môi trường JVM/OS. Máy chủ production, container và máy developer có thể có locale mặc định khác nhau. Nếu code ngầm dựa vào giá trị này, cùng một email có thể được render khác nhau giữa các môi trường.

Hãy cấu hình locale mặc định của ứng dụng rõ ràng:

```yaml
app:
  mail:
    default-locale: vi-VN
```

Sau đó chuyển thành `Locale` trong một thành phần chọn locale:

```java
import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class MailLocalePolicy {

    private final Locale defaultLocale;

    public MailLocalePolicy(
            @Value("${app.mail.default-locale:vi-VN}") String defaultTag
    ) {
        this.defaultLocale = Locale.forLanguageTag(defaultTag);
    }

    public Locale choose(String preferredLanguageTag) {
        if (preferredLanguageTag == null
                || preferredLanguageTag.isBlank()) {
            return defaultLocale;
        }

        Locale requested =
                Locale.forLanguageTag(preferredLanguageTag);

        if (requested.getLanguage().isBlank()) {
            return defaultLocale;
        }

        return requested;
    }
}
```

Ví dụ minh họa việc lấy một language tag và fallback khi giá trị trống. Ứng dụng thực tế nên kiểm tra locale được hỗ trợ, xử lý tag không hợp lệ và có thể chuẩn hóa `en` sang `en-US` theo danh sách locale mà sản phẩm cung cấp.

### Hỗ trợ một danh sách locale xác định

Không phải template nào cũng có mọi ngôn ngữ. Có thể khai báo danh sách hỗ trợ:

```java
import java.util.List;
import java.util.Locale;

public final class SupportedMailLocales {

    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("ja-JP")
    );

    private SupportedMailLocales() {}

    public static boolean supports(Locale candidate) {
        return SUPPORTED.contains(candidate);
    }
}
```

Nếu locale không hỗ trợ, chọn fallback theo chính sách và **ghi nhận locale thực sự được dùng**. Không nên âm thầm render `en-US` nhưng lưu metadata `ja-JP`, vì sau này sẽ không thể giải thích chính xác nội dung người nhận đã nhận.

## 4. Tổ chức message bundle theo locale

Spring cung cấp `MessageSource` để tra cứu thông điệp theo message code và locale. Cách phổ biến là dùng các file properties theo quy ước `ResourceBundle`.

Cấu trúc ví dụ:

```text
src/main/resources/
└── mail/
    ├── messages.properties
    ├── messages_vi.properties
    ├── messages_vi_VN.properties
    ├── messages_en.properties
    ├── messages_en_US.properties
    ├── messages_ja.properties
    └── messages_ja_JP.properties
```

Các file có ý nghĩa:

- `messages.properties`: bundle cơ sở hoặc ngôn ngữ fallback do ứng dụng quy định.
- `messages_vi.properties`: bản dịch chung cho tiếng Việt.
- `messages_vi_VN.properties`: bản dành riêng cho tiếng Việt tại Việt Nam.
- `messages_en_US.properties`: bản tiếng Anh theo quy ước Mỹ.
- `messages_ja_JP.properties`: bản tiếng Nhật tại Nhật Bản.

Với locale `vi-VN`, cơ chế bundle có thể tìm bản cụ thể `messages_vi_VN.properties`, rồi fallback theo ngôn ngữ `messages_vi.properties`, sau đó đến bundle cơ sở. Chính sách fallback thực tế còn chịu ảnh hưởng cấu hình `MessageSource`; hãy kiểm soát nó thay vì phụ thuộc ngầm vào locale của máy chủ.

### Ví dụ file tiếng Việt

```properties
mail.order.subject=Xác nhận đơn hàng {0}
mail.order.heading=Đơn hàng của bạn đã được xác nhận
mail.order.greeting=Xin chào {0},
mail.order.body=Đơn hàng {0} đã được xác nhận. Cảm ơn bạn đã mua hàng.
mail.order.cta=Theo dõi đơn hàng
mail.order.support=Cần hỗ trợ? Hãy liên hệ với chúng tôi.
```

### Ví dụ file tiếng Anh Mỹ

```properties
mail.order.subject=Order confirmation {0}
mail.order.heading=Your order is confirmed
mail.order.greeting=Hello {0},
mail.order.body=Order {0} has been confirmed. Thank you for your purchase.
mail.order.cta=Track your order
mail.order.support=Need help? Contact us.
```

Message code như `mail.order.subject` là định danh ổn định trong code. Giá trị thực thay đổi theo locale.

### Đặt encoding UTF-8 cho message bundle

Với `ResourceBundleMessageSource`, có thể cấu hình rõ encoding:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.ResourceBundleMessageSource;

@Configuration
public class MailMessageConfiguration {

    @Bean
    public MessageSource mailMessageSource() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();

        source.setBasenames("mail/messages");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);

        return source;
    }
}
```

`setBasenames("mail/messages")` trỏ tới các file bundle trong classpath, không cần thêm phần mở rộng `.properties`. `setDefaultEncoding("UTF-8")` chỉ định encoding khi đọc file. Tắt fallback theo system locale giúp kết quả không vô tình phụ thuộc locale máy chủ; fallback giữa các bundle theo language/region vẫn cần được thiết kế phù hợp.

Nếu dùng Spring Boot auto-configuration cho message source, có thể cấu hình:

```yaml
spring:
  messages:
    basename: mail/messages
    encoding: UTF-8
    fallback-to-system-locale: false
```

Tên property và khả năng binding cần tương ứng với phiên bản Spring Boot của dự án. Nếu ứng dụng tự khai báo bean `MessageSource`, hãy kiểm tra bean đó có thay thế hoặc bổ sung message source mà template engine sử dụng hay không.

## 5. Tra cứu subject theo locale bằng MessageSource

`MessageSource` có thể trả về nội dung theo code, tham số và locale:

```java
String subject = messageSource.getMessage(
        "mail.order.subject",
        new Object[] { orderNumber },
        locale
);
```

Nếu `locale` là `vi-VN`, subject lấy từ bundle tiếng Việt; nếu là `en-US`, nó lấy từ bundle tiếng Anh phù hợp.

Một service nhỏ:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.stereotype.Component;

@Component
public class MailSubjectResolver {

    private final MessageSource messageSource;

    public MailSubjectResolver(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String orderConfirmation(
            String orderNumber,
            Locale locale
    ) {
        return messageSource.getMessage(
                "mail.order.subject",
                new Object[] { orderNumber },
                locale
        );
    }
}
```

Dùng overload không truyền default message có nghĩa là **thiếu message code có thể phát sinh `NoSuchMessageException`**. Với email giao dịch, điều này thường tốt hơn việc gửi một subject trống hoặc vô tình dùng sai ngôn ngữ. Nếu nghiệp vụ có fallback, hãy thực hiện fallback có chủ đích và ghi nhận kết quả.

### Tham số trong message pattern

Trong file properties:

```properties
mail.order.subject=Order confirmation {0}
mail.order.greeting=Hello {0},
mail.order.item-count=You ordered {0} items.
```

`MessageSource` xử lý tham số theo quy tắc `MessageFormat`. Cần chú ý dấu nháy đơn trong pattern: `MessageFormat` dùng dấu nháy đơn để escape ký tự đặc biệt. Nếu nội dung bản dịch có dấu nháy đơn cần hiển thị, người dịch nên được hướng dẫn cách viết pattern đúng, ví dụ nhân đôi dấu nháy trong trường hợp cần thiết.

Đừng ghép câu từ những mảnh như `prefix + customerName + suffix` khi cấu trúc ngữ pháp có thể khác giữa các ngôn ngữ. Hãy đặt cả câu trong message bundle với placeholder.

## 6. Bản địa hóa HTML template bằng Thymeleaf

Message bundle phù hợp với subject, CTA và các chuỗi giao diện. Với email có bố cục HTML, có thể dùng template riêng theo locale hoặc kết hợp template chung với message key.

### 6.1. Template riêng theo locale

Ví dụ:

```text
mail/
└── order-confirmation/
    ├── v1/
    │   ├── vi-VN.html
    │   ├── en-US.html
    │   └── ja-JP.html
    └── v2/
        ├── vi-VN.html
        ├── en-US.html
        └── ja-JP.html
```

Template tiếng Việt:

```html
<!doctype html>
<html lang="vi" dir="ltr">
<head>
  <meta charset="UTF-8">
  <title>Xác nhận đơn hàng</title>
</head>
<body>
  <main>
    <h1>Đơn hàng của bạn đã được xác nhận</h1>
    <p>Xin chào <span th:text="${customerName}">bạn</span>,</p>
    <p>
      Mã đơn hàng:
      <strong th:text="${orderNumber}">ORD-001</strong>
    </p>
    <a th:href="${trackingUrl}">Theo dõi đơn hàng</a>
  </main>
</body>
</html>
```

Template tiếng Anh có thể có thứ tự và cách diễn đạt khác:

```html
<!doctype html>
<html lang="en" dir="ltr">
<head>
  <meta charset="UTF-8">
  <title>Order confirmation</title>
</head>
<body>
  <main>
    <h1>Your order is confirmed</h1>
    <p>Hello <span th:text="${customerName}">customer</span>,</p>
    <p>
      Order number:
      <strong th:text="${orderNumber}">ORD-001</strong>
    </p>
    <a th:href="${trackingUrl}">Track your order</a>
  </main>
</body>
</html>
```

Template riêng cho phép người biên tập điều chỉnh bố cục, cách xưng hô và trật tự nội dung theo ngôn ngữ. Nhược điểm là nhiều file có thể lặp cấu trúc và cần đồng bộ khi thêm trường dữ liệu mới.

### 6.2. Dùng message expression trong Thymeleaf

Có thể giữ cấu trúc HTML chung và lấy chuỗi từ `MessageSource`:

```html
<!doctype html>
<html lang="vi" dir="ltr">
<body>
  <main>
    <h1 th:text="#{mail.order.heading}">Order confirmed</h1>
    <p th:text="#{mail.order.greeting(${customerName})}">
      Hello, customer
    </p>
    <p>
      <span th:text="#{mail.order.number-label}">Order number</span>:
      <strong th:text="${orderNumber}">ORD-001</strong>
    </p>
    <a th:href="${trackingUrl}"
       th:text="#{mail.order.cta}">Track your order</a>
  </main>
</body>
</html>
```

Trong Thymeleaf:

- `#{...}` tra cứu message theo locale của context.
- `${...}` đọc biến dữ liệu được đưa vào context.
- `th:text` ghi nội dung text và escape HTML theo mặc định.
- `th:href` đặt giá trị vào thuộc tính URL; URL vẫn cần được kiểm tra trước đó.

Cấu trúc chung phù hợp khi các ngôn ngữ có bố cục tương tự. Khi ngôn ngữ có trật tự câu hoặc bố cục khác đáng kể, template riêng theo locale có thể rõ ràng hơn.

### 6.3. Cấu hình SpringTemplateEngine

Với ứng dụng dùng Thymeleaf Spring integration, có thể cấu hình engine cho email:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

@Configuration
public class MailTemplateConfiguration {

    @Bean
    public SpringTemplateEngine mailTemplateEngine(
            MessageSource mailMessageSource
    ) {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();

        resolver.setPrefix("mail/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(true);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);
        engine.setMessageSource(mailMessageSource);
        return engine;
    }
}
```

`SpringTemplateEngine` cung cấp tích hợp Spring, bao gồm message expression và Spring dialect. Package `org.thymeleaf.spring6` phù hợp với Thymeleaf integration cho Spring 6; ứng dụng dùng phiên bản Spring/Thymeleaf khác cần dependency và package tương ứng.

## 7. Render template theo locale cụ thể

Không nên để renderer tự lấy locale máy chủ. Hãy truyền `Locale` vào mỗi lần render:

```java
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Component
public class LocalizedMailTemplateRenderer {

    private final SpringTemplateEngine templateEngine;

    public LocalizedMailTemplateRenderer(
            SpringTemplateEngine templateEngine
    ) {
        this.templateEngine = templateEngine;
    }

    public String render(
            String templateName,
            Locale locale,
            Map<String, Object> variables
    ) {
        Context context = new Context(locale);
        context.setVariables(variables);

        return templateEngine.process(templateName, context);
    }
}
```

Ví dụ:

```java
String html = renderer.render(
        "order-confirmation/v2/vi-VN",
        Locale.forLanguageTag("vi-VN"),
        Map.of(
                "customerName", "Nguyễn An",
                "orderNumber", "ORD-2026-001",
                "trackingUrl",
                "https://shop.example.org/orders/ORD-2026-001"
        )
);
```

`Context(locale)` cung cấp locale cho message expression trong template. Đường dẫn template và locale được truyền riêng vì **template key/version** và **ngôn ngữ render** là hai chiều quản lý khác nhau.

Nếu dùng một template chung với message bundle, template name có thể chỉ gồm key/version; locale vẫn được đưa qua `Context`. Nếu dùng file HTML riêng theo locale, template name có thể chứa language tag, như `order-confirmation/v2/vi-VN`.

## 8. Gửi subject, plain text và HTML cùng locale

Một email hoàn chỉnh nên tạo cả ba phần nội dung theo cùng một locale:

1. Subject được tra cứu từ message bundle.
2. Plain text được lấy từ bundle hoặc template text riêng.
3. HTML được render từ template theo locale.

Ví dụ một service:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Map;
import org.springframework.context.MessageSource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class LocalizedOrderMailer {

    private final JavaMailSender mailSender;
    private final MessageSource mailMessageSource;
    private final LocalizedMailTemplateRenderer renderer;

    public LocalizedOrderMailer(
            JavaMailSender mailSender,
            MessageSource mailMessageSource,
            LocalizedMailTemplateRenderer renderer
    ) {
        this.mailSender = mailSender;
        this.mailMessageSource = mailMessageSource;
        this.renderer = renderer;
    }

    public void sendConfirmation(
            String recipient,
            String orderNumber,
            String customerName,
            String trackingUrl,
            Locale locale
    ) throws MessagingException {

        String subject = mailMessageSource.getMessage(
                "mail.order.subject",
                new Object[] { orderNumber },
                locale
        );

        String plainText = mailMessageSource.getMessage(
                "mail.order.body",
                new Object[] { orderNumber, trackingUrl },
                locale
        );

        String html = renderer.render(
                "order-confirmation/v2/" + locale.toLanguageTag(),
                locale,
                Map.of(
                        "customerName", customerName,
                        "orderNumber", orderNumber,
                        "trackingUrl", trackingUrl
                )
        );

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.org", "Example Store");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, html);

        mailSender.send(message);
    }
}
```

Ví dụ giả định các message code và template tương ứng đã tồn tại cho locale được chọn. Trong ứng dụng thực tế, kiểm tra locale được hỗ trợ, đảm bảo template có đủ biến, xây dựng URL từ domain tin cậy, dùng tên hiển thị người gửi bản địa hóa nếu cần và giữ subject/plain/HTML cùng version.

Constructor `MimeMessageHelper(message, true, "UTF-8")` bật multipart, cần thiết cho hai bản plain/HTML. Charset UTF-8 hỗ trợ ký tự tiếng Việt, tiếng Nhật và các ký tự Unicode khác trong body/header. Nó không tự chuyển một địa chỉ email có local-part Unicode thành địa chỉ SMTPUTF8 hợp lệ.

### Không để subject lấy một locale còn body lấy locale khác

Một lỗi thiết kế thường gặp là subject được tạo từ `LocaleContextHolder.getLocale()` trong request, trong khi worker render HTML bằng locale mặc định. Kết quả có thể là subject tiếng Anh nhưng body tiếng Việt.

Hãy chọn locale **một lần** trong nghiệp vụ, sau đó truyền cùng giá trị cho subject resolver, plain text renderer và HTML renderer. Ghi locale đã dùng vào metadata của yêu cầu gửi nếu cần audit.

## 9. Định dạng ngày giờ theo locale và time zone

Ngày giờ thường xuất hiện trong email xác nhận đặt chỗ, lịch hẹn, hóa đơn hoặc thông báo giao hàng. Cần hai đầu vào:

- `Locale`: cách viết ngày, tên tháng và thứ tự thành phần.
- `ZoneId`: múi giờ để chuyển một thời điểm thành giờ địa phương.

Ví dụ:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

Instant appointment = Instant.parse("2026-11-12T09:30:00Z");

Locale locale = Locale.forLanguageTag("vi-VN");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

DateTimeFormatter formatter =
        DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.LONG)
                .withLocale(locale)
                .withZone(zone);

String localizedDate = formatter.format(appointment);
```

Cùng một `Instant` có thể hiển thị khác nhau khi đổi locale hoặc time zone. Điều đó không có nghĩa thời điểm sự kiện đã thay đổi.

**Không dùng locale để suy ra time zone.** Hãy lấy time zone từ profile người dùng hoặc dữ liệu lịch hẹn. Nếu email liên quan đến thời hạn pháp lý, cần hiển thị múi giờ hoặc tên vùng rõ ràng để người nhận không hiểu nhầm.

### Tránh format ngày giờ ở quá sớm

Không lưu ngày giờ đã format thành chuỗi rồi tái sử dụng cho tất cả locale. Hãy lưu thời điểm chuẩn như `Instant`, `OffsetDateTime` hoặc kiểu dữ liệu thời gian phù hợp, rồi format khi render email. Điều này giúp tạo lại email cho locale khác mà không mất thông tin gốc.

## 10. Định dạng số, tiền tệ và đơn vị đo

`NumberFormat` có thể format số theo locale:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

BigDecimal amount = new BigDecimal("1250000.50");

Locale vietnamese = Locale.forLanguageTag("vi-VN");
NumberFormat numberFormat =
        NumberFormat.getNumberInstance(vietnamese);

String number = numberFormat.format(amount);
```

Đối với tiền tệ, lấy **currency code từ giao dịch** rồi format theo locale:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

BigDecimal total = new BigDecimal("1250000");
String currencyCode = "VND";

Locale locale = Locale.forLanguageTag("vi-VN");

NumberFormat formatter =
        NumberFormat.getCurrencyInstance(locale);

formatter.setCurrency(Currency.getInstance(currencyCode));

String localizedAmount = formatter.format(total);
```

Locale ảnh hưởng đến dấu phân cách, vị trí ký hiệu và cách trình bày; currency code xác định đơn vị tiền thực tế. Không nên thay VND thành USD chỉ vì email được gửi bằng tiếng Anh.

Với đơn vị đo, cần biết đơn vị gốc và chính sách chuyển đổi. Ví dụ một kiện hàng có khối lượng 2 kg; nếu người nhận ở thị trường dùng pound, hệ thống có thể chuyển đổi sang đơn vị tương ứng và ghi rõ đơn vị. Đừng chỉ đổi ký hiệu `kg` thành `lb` mà giữ nguyên con số.

### Dùng giá trị có kiểu, không dùng chuỗi đã format làm dữ liệu gốc

Nên giữ `BigDecimal`, `Currency`, `Instant`, `ZoneId` và các kiểu dữ liệu phù hợp cho tới bước render. Chuỗi đã format là **đầu ra theo locale**, không nên dùng làm dữ liệu tính toán hoặc lưu làm giá trị giao dịch gốc.

## 11. Bản địa hóa số nhiều và câu có tham số

Các ngôn ngữ có quy tắc số nhiều khác nhau. Ví dụ tiếng Anh có thể phân biệt `1 item` và `2 items`; một số ngôn ngữ có nhiều category số nhiều hơn `one` và `other`.

Không nên tạo câu bằng cách nối:

```java
String text = count + " item(s)";
```

Cách này không tự nhiên và khó dịch. Có thể dùng message pattern cho trường hợp đơn giản:

```properties
mail.cart.count=You have {0} items in your cart.
```

Nhưng `MessageFormat` không cung cấp đầy đủ mọi quy tắc plural/gender của các ngôn ngữ. Với nội dung có số nhiều phức tạp, cân nhắc **ICU MessageFormat** hoặc một hệ thống localization hỗ trợ plural/select theo CLDR.

Một pattern khái niệm:

```text
{count, plural,
    one {You have one item}
    other {You have # items}
}
```

Đây là cú pháp minh họa ICU MessageFormat, không phải cú pháp `java.text.MessageFormat` mặc định. Cần thêm thư viện và cấu hình phù hợp nếu sử dụng.

Ngoài số nhiều, câu có thể cần lựa chọn theo giới tính ngữ pháp, loại sản phẩm hoặc trạng thái nghiệp vụ. Hãy trao đổi với người dịch về ngữ cảnh của từng message code; một chuỗi ngắn tách khỏi ngữ cảnh thường khó dịch chính xác.

## 12. Bản địa hóa nội dung HTML và ngôn ngữ hiển thị

HTML email nên khai báo ngôn ngữ của tài liệu:

```html
<html lang="vi" dir="ltr">
```

Với ngôn ngữ đọc từ phải sang trái như tiếng Ả Rập hoặc Hebrew, cần xem xét thuộc tính `dir`:

```html
<html lang="ar" dir="rtl">
```

Một số lưu ý:

- Đặt `lang` phù hợp với locale để trình đọc màn hình và công cụ hỗ trợ hiểu ngôn ngữ.
- Với RTL, kiểm tra căn lề, thứ tự icon, dấu câu, số và liên kết.
- Không giả định chỉ đổi `text-align: right` là đủ để chuyển layout sang RTL.
- Dùng CSS email tương thích; nhiều client không hỗ trợ đầy đủ CSS hiện đại.
- Dùng font có glyph phù hợp với các hệ chữ được hỗ trợ.
- Giữ alt text cho ảnh và đảm bảo thông tin quan trọng có trong văn bản.
- Kiểm tra cách trộn chữ RTL với mã đơn hàng, URL và số điện thoại LTR.

Nếu locale quyết định hướng hiển thị, hãy truyền một biến `textDirection` được xác định từ danh sách locale hỗ trợ thay vì chèn chuỗi tùy ý vào thuộc tính HTML.

## 13. Fallback khi thiếu bản dịch hoặc template

Một hệ thống bản địa hóa cần quy định rõ điều gì xảy ra khi không có bản dịch cho locale yêu cầu.

Ví dụ người dùng chọn `ja-JP`, nhưng email xác nhận đơn hàng mới chỉ có `vi-VN` và `en-US`. Một chính sách có thể là:

```text
ja-JP
  ↓ không có bản dịch vùng
ja
  ↓ không có bundle tiếng Nhật
application default: en-US
  ↓ render và ghi nhận resolvedLocale=en-US
```

Các cấp fallback thường gồm:

1. Locale đầy đủ, ví dụ `ja-JP`.
2. Language-only, ví dụ `ja`.
3. Locale mặc định được sản phẩm công bố, ví dụ `en-US`.
4. Nếu vẫn không có message/template, **fail render rõ ràng** thay vì gửi email thiếu nội dung.

### Fallback message bundle và fallback HTML template là hai việc riêng

`MessageSource` có thể tìm được `mail.order.subject` từ bundle cơ sở, nhưng template HTML `order-confirmation/v2/ja-JP.html` vẫn có thể không tồn tại. Ngược lại, HTML template có thể tồn tại nhưng một message code trong đó lại thiếu.

Cần xử lý cả hai nguồn:

- Message bundle: kiểm tra message code và fallback locale.
- Template: kiểm tra file/template name và version.
- Plain text: kiểm tra có bản tương ứng hay không.
- Subject: kiểm tra không rỗng và cùng locale với body.

### Không fallback âm thầm

Nếu locale yêu cầu là `ja-JP` nhưng hệ thống gửi `en-US`, cần ghi nhận điều đó. Có thể chấp nhận fallback nếu sản phẩm đã quy định, nhưng nên lưu cả:

```text
requestedLocale = ja-JP
resolvedLocale  = en-US
fallbackReason  = TEMPLATE_NOT_AVAILABLE
```

Thông tin này giúp giải thích vì sao người dùng nhận email bằng ngôn ngữ khác với lựa chọn trong profile. Với email pháp lý hoặc nội dung bắt buộc theo thị trường, fallback có thể không được phép; khi đó nên chặn việc tạo yêu cầu gửi cho tới khi có bản dịch được duyệt.

## 14. Locale phải được truyền qua tác vụ bất đồng bộ

Một lỗi thường gặp trong hệ thống gửi mail bằng queue là dựa vào `LocaleContextHolder` trong worker.

Trong HTTP request đồng bộ, Spring có thể đặt locale vào context của thread. Nhưng khi tạo tác vụ bất đồng bộ hoặc đẩy message vào queue, worker có thể chạy trên **thread khác, process khác hoặc máy khác**. Thread-local context của request không tự truyền qua queue.

Không nên làm:

```java
// Trong worker, không nên giả định locale request ban đầu vẫn tồn tại.
Locale locale = LocaleContextHolder.getLocale();
```

Thay vào đó, chọn locale khi tạo yêu cầu và lưu vào event/outbox:

```java
public record EmailRequested(
        String messageId,
        String recipient,
        String templateKey,
        String templateVersion,
        String requestedLocaleTag,
        String resolvedLocaleTag,
        String payloadJson
) {
}
```

Khi worker xử lý:

```java
Locale locale =
        Locale.forLanguageTag(record.resolvedLocaleTag());

String subject = messageSource.getMessage(
        "mail.order.subject",
        new Object[] { orderNumber },
        locale
);
```

Điều này làm kết quả ổn định giữa các instance và giúp audit. Nếu chính sách yêu cầu quyết định locale tại thời điểm gửi, worker có thể gọi locale policy bằng dữ liệu profile đã lưu, nhưng **quy tắc đó phải được ghi rõ**. Không nên để kết quả phụ thuộc thread-local vô tình.

### LocaleContextHolder dùng khi nào?

`LocaleContextHolder` hữu ích khi xử lý đồng bộ trong request và ứng dụng đã cấu hình `LocaleResolver`/`LocaleContextResolver`. Ví dụ controller có thể dùng locale đã được chọn từ HTTP request. Nhưng khi tạo công việc nền, hãy trích xuất locale thành dữ liệu tường minh trước khi kết thúc request.

Không dùng `LocaleContextHolder` như nơi lưu preference lâu dài của người dùng.

## 15. Bản địa hóa kết hợp với version template

Locale và template version là hai chiều độc lập:

```text
templateKey = order-confirmation
templateVersion = v3
locale = vi-VN
variant = default
```

Một template có thể có version `v3` cho nhiều ngôn ngữ. Cần chọn chính sách:

**Version chung cho mọi locale:** `v3` là một release bao gồm `vi-VN`, `en-US`, `ja-JP`. Nếu bản dịch tiếng Nhật chưa sẵn sàng, không đánh dấu toàn bộ release hoàn chỉnh hoặc quy định fallback rõ ràng.

**Version riêng theo locale:** `vi-VN/v3`, `en-US/v2`, `ja-JP/v1`. Cách này linh hoạt nhưng record gửi phải lưu version của đúng locale.

Dù chọn cách nào, email đã được tạo nên ghi lại ít nhất:

```json
{
  "messageId": "mail-12345",
  "templateKey": "order-confirmation",
  "templateVersion": "v3",
  "requestedLocale": "vi-VN",
  "resolvedLocale": "vi-VN",
  "variant": "default"
}
```

Nếu nội dung message bundle thay đổi độc lập với HTML template, nên gắn chúng với cùng release ID hoặc content hash. Nếu không, cùng template version có thể render subject khác nhau sau khi bundle bị cập nhật.

**Version đã phát hành nên bất biến.** Nếu thay đổi bản dịch hoặc câu chữ, tạo version/release mới và giữ nội dung cũ cho các yêu cầu pending đang tham chiếu.

## 16. Bảo mật và dữ liệu không tin cậy trong email đã bản địa hóa

Bản dịch không làm thay đổi các yêu cầu bảo mật của HTML email.

- Dùng `th:text` để đưa dữ liệu vào text node với HTML escaping.
- Kiểm tra URL trước khi đưa vào `th:href`.
- Không cho phép dữ liệu người dùng trở thành HTML thô nếu chưa được sanitize theo chính sách.
- Không đưa secret, token nội bộ hoặc dữ liệu không cần thiết vào email.
- Kiểm tra biến động trong subject để tránh header injection; dùng API của `MimeMessageHelper`, không ghép raw header.
- Không giả định bản dịch do bên ngoài cung cấp luôn an toàn để render.
- Kiểm soát quyền sửa và phát hành template/bundle.

Một bản dịch có thể chứa ký tự đặc biệt, dấu nháy, dấu xuống dòng hoặc placeholder sai. Cần kiểm thử dữ liệu trước khi release, đặc biệt với message pattern dùng `MessageFormat`.

## 17. Kiểm thử bản địa hóa subject và body

Kiểm thử một locale duy nhất không đủ nếu email có nhiều bản dịch. Nên có ma trận test theo **template key × version × locale**.

| Kiểm thử | Điều cần xác nhận |
|---|---|
| Message bundle lookup | Các code bắt buộc tồn tại cho locale hỗ trợ. |
| Subject rendering | Subject đúng ngôn ngữ, có tham số và không còn placeholder. |
| Plain text rendering | Có nội dung đầy đủ, CTA và thông tin quan trọng. |
| HTML rendering | Template load đúng locale/version, không còn biến chưa resolve. |
| Unicode | Tiếng Việt, tiếng Nhật, dấu câu và ký tự đặc biệt hiển thị đúng. |
| Number/date/currency | Format theo locale, time zone và currency của dữ liệu. |
| RTL | Hướng đọc, căn lề, URL và mã định danh hiển thị được. |
| Fallback | Locale thiếu bản dịch được xử lý theo chính sách đã định. |
| Async | Worker dùng đúng locale đã lưu, không dựa vào request thread. |
| MIME integration | Subject, text và HTML có charset đúng và được đóng gói hợp lệ. |

### Ví dụ kiểm thử MessageSource

```java
@Test
void resolvesOrderSubjectInVietnamese() {
    Locale locale = Locale.forLanguageTag("vi-VN");

    String subject = messageSource.getMessage(
            "mail.order.subject",
            new Object[] { "ORD-001" },
            locale
    );

    assertThat(subject).contains("Xác nhận đơn hàng");
    assertThat(subject).contains("ORD-001");
}
```

Một test khác cho tiếng Anh nên xác nhận subject lấy từ bundle tiếng Anh, không phải bundle mặc định.

### Kiểm thử fallback có chủ đích

Nếu `ja-JP` chưa có bản dịch và chính sách cho phép fallback `en-US`, test cần xác nhận:

- `requestedLocale` vẫn là `ja-JP`.
- `resolvedLocale` được ghi là `en-US`.
- Subject, plain text và HTML đều dùng cùng `en-US`.
- Log/metadata ghi lý do fallback.
- Không có phần nào còn dùng `ja-JP` trong khi phần khác dùng `en-US`.

### Kiểm tra email thực tế

Có thể dùng Mailpit hoặc GreenMail trong môi trường test để nhận email. Kiểm tra header `Subject` được mã hóa và giải mã đúng; `Content-Type` của text/HTML có charset phù hợp; nội dung Unicode không bị biến thành ký tự lỗi; plain text và HTML truyền đạt cùng thông tin; locale được ghi trong metadata của yêu cầu gửi.

SMTP test server không mô phỏng đầy đủ renderer của Gmail, Outlook hoặc Apple Mail. Với email quan trọng, cần xem kết quả trên các client và thiết bị mục tiêu, nhất là với RTL và font CJK.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Subject tiếng Anh, body tiếng Việt | Hai phần dùng locale được resolve riêng | Chọn locale một lần và truyền cho mọi renderer. |
| Body rơi về bundle mặc định | Thiếu locale-specific message hoặc fallback chưa rõ | Kiểm tra file properties và resolved locale. |
| HTML không render được nhưng subject có bản dịch | Thiếu template file cho locale/version | Kiểm tra template catalog và chính sách fallback. |
| Worker gửi email bằng locale máy chủ | Locale không được lưu trong queue/outbox | Lưu language tag vào record và truyền tường minh. |
| Tên tháng hoặc số tiền không đúng vùng | Dùng format mặc định JVM hoặc nối chuỗi thủ công | Dùng `DateTimeFormatter`/`NumberFormat` với locale rõ ràng. |
| Múi giờ hiển thị sai | Suy ra `ZoneId` từ locale hoặc dùng timezone mặc định | Lưu và sử dụng ZoneId riêng. |
| Giá tiền sai currency | Lấy currency từ locale thay vì giao dịch | Lấy currency code từ dữ liệu nghiệp vụ. |
| Câu dịch thiếu hoặc sai ngữ pháp | Nối các mảnh câu, placeholder không đúng | Dùng message pattern đầy đủ và review bản dịch. |
| HTML bị lỗi ở ngôn ngữ RTL | Chỉ đổi căn lề, không xử lý direction và mixed text | Dùng `dir`, kiểm tra layout và client thực tế. |
| Tiếng Việt/Japanese bị lỗi dấu | File bundle/template hoặc MIME charset không nhất quán | Dùng UTF-8 từ file nguồn đến `MimeMessageHelper`. |
| Email cũ dùng bản dịch mới ngoài dự kiến | Worker lấy `latest` thay vì version đã pin | Ghi version/release trong outbox. |
| Subject chứa `{0}` nguyên văn | Message pattern không được resolve hoặc thiếu argument | Kiểm tra message code, tham số và `MessageSource`. |

## 19. Kiến trúc đề xuất cho email đa ngôn ngữ

Có thể tách trách nhiệm thành các thành phần:

```text
Business event
    |
    v
Mail request / outbox
    ├── templateKey
    ├── templateVersion
    ├── requestedLocale
    ├── resolvedLocale
    ├── recipient
    └── payload
         |
         v
Locale policy
         |
         v
Template + MessageSource renderer
    ├── subject
    ├── plain text
    └── HTML
         |
         v
MimeMessage builder
         |
         v
JavaMailSender
         |
         v
SMTP provider
```

Mỗi phần có một nhiệm vụ:

- **Business event:** cung cấp dữ liệu nghiệp vụ cần thông báo.
- **Mail request/outbox:** giữ recipient, template version, locale và payload cần render.
- **Locale policy:** chọn locale theo profile, giao dịch hoặc fallback.
- **Renderer:** tra message bundle và render subject/plain/HTML.
- **Message builder:** tạo `MimeMessage`, đặt header, charset và MIME parts.
- **JavaMailSender:** gửi thông điệp tới SMTP.
- **Delivery tracker:** ghi nhận SMTP result, bounce và delivery event nếu nhà cung cấp hỗ trợ.

Tách như vậy giúp có thể thay template engine hoặc thêm ngôn ngữ mà không phải viết lại logic gửi SMTP. Nó cũng giúp kiểm thử bản dịch độc lập với việc kết nối máy chủ mail.

## 20. Ghi nhớ

- **Locale** xác định ngôn ngữ và quy ước vùng; nó không tự xác định time zone hoặc currency của giao dịch.
- Chọn locale bằng chính sách rõ ràng: preference người dùng, locale giao dịch, request preference và default của ứng dụng.
- Dùng **`MessageSource` và resource bundle** để tra cứu subject, CTA, footer và các chuỗi có tham số.
- Dùng **Thymeleaf/SpringTemplateEngine** hoặc template engine phù hợp để render HTML theo locale; giữ plain text tương ứng.
- Truyền **cùng một locale** cho subject, plain text và HTML. Khi xử lý bất đồng bộ, lưu language tag trong outbox thay vì dựa vào `LocaleContextHolder` của request.
- Dùng `DateTimeFormatter` và `NumberFormat` với locale rõ ràng; time zone và currency lấy từ dữ liệu nghiệp vụ tương ứng.
- Dùng UTF-8 cho message bundle, template và `MimeMessageHelper`; kiểm tra cả subject lẫn body.
- Quy định fallback rõ ràng, ghi nhận `requestedLocale` và `resolvedLocale`, không âm thầm gửi bằng ngôn ngữ khác.
- Version hóa template/bundle để có thể tái hiện nội dung email đã gửi; kiểm thử theo từng template version và locale.
- Kiểm tra HTML escaping, URL, RTL, Unicode và cách hiển thị trên mail client mục tiêu.

Bản địa hóa email tốt bắt đầu từ việc **chọn đúng locale**, sau đó dùng locale đó nhất quán để tạo subject, plain text, HTML và các giá trị được format. Khi locale, template version và dữ liệu nghiệp vụ được ghi nhận rõ ràng, Spring Mail có thể gửi những email nhất quán, dễ kiểm thử và có thể truy xuất khi cần điều tra hoặc thay đổi nội dung.
