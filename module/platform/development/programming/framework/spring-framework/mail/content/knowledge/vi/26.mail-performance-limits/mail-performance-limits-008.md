# Giảm số lần render template không cần thiết

Trong Spring Framework Mail, một email thường được dựng từ dữ liệu nghiệp vụ, template HTML/plain text và thông tin người nhận. Nếu ứng dụng render cùng một nội dung nhiều lần trước khi gọi **JavaMailSender.send(...)**, chi phí CPU, bộ nhớ, truy vấn dữ liệu và thời gian xử lý có thể tăng mà không tạo thêm giá trị cho người nhận.

Ví dụ: hệ thống render email xác nhận đơn hàng một lần để kiểm tra nội dung, một lần để tạo MimeMessage và một lần nữa khi worker retry do SMTP server tạm thời trả lỗi. Nếu cùng một template, cùng dữ liệu và cùng phiên bản nội dung được sử dụng, nhiều lượt render có thể là công việc dư thừa. Tuy nhiên, **không được render một nội dung cá nhân hóa rồi dùng chung cho các người nhận khác nhau** chỉ để tiết kiệm tài nguyên.

Bài học này tập trung vào **giảm số lần render template không cần thiết** một cách an toàn trong chương **Hiệu năng và giới hạn** của Spring Framework Mail. Những câu hỏi chính:

- Đâu là một lần render thực sự?
- Khi nào cache template đã parse giúp ích và khi nào nó chưa đủ?
- Làm sao chỉ render một lần trong một luồng tạo email?
- Khi gửi nhiều recipient, phần nào được phép dùng chung?
- Với outbox/retry, nên lưu dữ liệu render hay lưu kết quả HTML?
- Cache key, TTL, template version, tenant và locale ảnh hưởng thế nào?
- Làm sao đo số lượt render và kiểm thử không render lặp?
- Khi nào **phải render lại** để tránh nội dung cũ, token hết hạn hoặc rò rỉ dữ liệu?

Mục tiêu là **gửi đúng nội dung với ít công việc lặp hơn**, không đánh đổi tính chính xác nghiệp vụ hay bảo mật thông tin khách hàng.

## 1. Render template nằm ở đâu trong luồng gửi?

Một luồng gửi email HTML điển hình:

~~~text
Business event / request
           |
           v
Validate recipient and eligibility
           |
           v
Load immutable mail view model
           |
           v
Select template, version and locale
           |
           v
TemplateEngine.process(...)
           |
           v
Rendered HTML / plain-text content
           |
           v
MimeMessageHelper.setText(...)
           |
           v
JavaMailSender.send(...)
           |
           v
SMTP relay
~~~

**Render** là bước template engine kết hợp dữ liệu với template để tạo chuỗi kết quả. Chẳng hạn, Thymeleaf xử lý các biểu thức, điều kiện, vòng lặp và fragments rồi trả về HTML.

Ví dụ:

~~~java
String html = templateEngine.process(
        "order-confirmation",
        context
);
~~~

Đây là một lượt render. Sau đó:

~~~java
helper.setText(plainText, html);
~~~

đưa chuỗi nội dung đã có vào MIME message. **Không cần gọi template engine lại** nếu nội dung đã chuẩn bị chính xác.

### 1.1. Render không phải là SMTP send

Một template đã render thành công vẫn có thể gặp lỗi khi gửi: AUTH sai, TLS lỗi, recipient bị từ chối, provider tạm quá tải, attachment quá lớn hoặc timeout sau DATA. Ngược lại, giảm render không giải quyết trực tiếp độ trễ kết nối SMTP.

### 1.2. Render không phải là parse template

Template engine có thể cache cấu trúc template đã được đọc/parse. Nhưng mỗi lần gọi process với một Context vẫn có thể tạo một chuỗi output mới. Cần phân biệt hai loại cache.

## 2. Vì sao render nhiều lần tạo overhead?

Một lượt render có thể bao gồm:

- Chọn template theo tên.
- Parse template nếu chưa có trong cache.
- Thực thi expressions và logic điều kiện.
- Xử lý layout, fragments, danh sách item.
- Định dạng ngày, thời gian và tiền tệ.
- Escape HTML và xây dựng chuỗi output.
- Cấp phát các object, buffer và chuỗi trung gian.
- Thực hiện lời gọi dữ liệu bên ngoài nếu template được thiết kế không tốt.

Một template HTML có bảng hàng trăm dòng sản phẩm sẽ tiêu tốn nhiều hơn một đoạn văn bản đơn giản. Nếu render ba lần mà chỉ dùng một output, hai lượt dư thừa có thể làm tăng tải không cần thiết.

Ví dụ chỉ để hình dung quy mô:

| Số mail event | Lượt HTML render/event | Tổng lượt render |
| ---: | ---: | ---: |
| 10.000 | 3 | 30.000 |
| 10.000 | 2 | 20.000 |
| 10.000 | 1 | 10.000 |

Bảng **chỉ đếm invocation**, không tuyên bố tổng latency sẽ giảm tỷ lệ thuận. Nếu SMTP và queue đang là bottleneck, giảm render có thể không tạo khác biệt lớn cho thời gian tới relay, dù CPU được cải thiện.

## 3. Ba dạng cache khác nhau

| Dạng cache | Dữ liệu được giữ | Lợi ích | Rủi ro |
| --- | --- | --- | --- |
| **Parsed-template cache** | Cấu trúc template đã parse | Giảm đọc/parse file | Chưa thấy template mới nếu không invalidate |
| **Rendered-output cache** | HTML/text sau khi thay dữ liệu | Tránh render cùng nội dung | Dùng nhầm dữ liệu, stale content, lộ PII |
| **View-model/data cache** | Dữ liệu cần cho template | Tránh lấy dữ liệu lặp | Dữ liệu nghiệp vụ cũ, sai scope |
| **Static-fragment cache** | Nội dung chung | Giảm xử lý fragment không thay đổi | Cần version/tenant/locale đúng |

### 3.1. Parsed-template cache không loại bỏ các lượt process

~~~java
String htmlA = engine.process(
        "order-confirmation",
        contextA
);

String htmlB = engine.process(
        "order-confirmation",
        contextB
);
~~~

Ngay cả khi engine cache template đã parse, đây vẫn là hai lần render output.

### 3.2. Output reuse mới giảm số lần render

~~~java
RenderedMail content = renderer.render(view);

// Chỉ dùng content.html() và content.plainText().
// Không gọi renderer.render(view) lần nữa để lấy từng phần.
~~~

Tái sử dụng một object kết quả ở cùng phạm vi công việc là cách đơn giản, thường an toàn hơn cache output toàn cục.

### 3.3. Không cache sai thứ cần tối ưu

Nếu thời gian chậm là tạo PDF, cache HTML không thay thế cache tài liệu. Nếu template đang thực hiện nhiều truy vấn database, nên tách dữ liệu ra view model và tối ưu truy vấn trước khi thêm HTML cache phức tạp.

## 4. Nguyên tắc một ý định gửi, một bộ nội dung

Một mail event nên có định danh rõ:

~~~text
eventId: ORDER_CONFIRMED:1001:v3
recipientRef: customer-42
templateId: order-confirmation
templateVersion: v4
locale: vi-VN
~~~

Nếu nội dung của event này đã được xác định và không thay đổi qua các bước xử lý, hãy chuẩn bị **RenderedMail** một lần rồi truyền object đó tới các bước dựng MIME, lưu trạng thái hoặc retry theo chính sách.

~~~text
Mail event
    |
    v
Validated immutable view model
    |
    v
Render once
    |
    +-- Subject
    +-- HTML
    +-- Plain text
    |
    v
Prepared content
    |
    +-- Build MIME
    +-- Persist snapshot if needed
    +-- Submit through SMTP
~~~

**Render một lần** ở đây không nhất thiết có nghĩa chỉ một lệnh templateEngine.process: nếu có hai template độc lập cho HTML và text/plain, hai lượt render có thể hoàn toàn hợp lệ. Ý nghĩa là **không gọi lại cùng phép render vô ích**.

## 5. Tạo view model tách khỏi JPA entity

Ví dụ record Java:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Locale;

public record OrderMailView(
        String eventId,
        String recipient,
        String customerName,
        String orderNumber,
        BigDecimal totalAmount,
        Instant confirmedAt,
        Locale locale
) {}
~~~

Một view model chỉ chứa dữ liệu template thực sự dùng sẽ dễ tạo snapshot, kiểm thử và cache đúng hơn là đưa cả entity vào template engine.

### 5.1. Tránh template truy vấn database

Nếu template expression truy cập entity lazily loaded, mỗi lượt render có thể:

- Kích hoạt N+1 queries.
- Phụ thuộc persistence context còn mở.
- Đọc trạng thái khác nhau giữa các lần render.
- Kéo dài transaction dữ liệu.
- Tạo lỗi lazy initialization trong worker.

Nên lấy dữ liệu cần thiết ở tầng nghiệp vụ, chuyển sang DTO bất biến và render **ngoài transaction database kéo dài** khi phù hợp.

### 5.2. Bất biến cũng phải áp dụng cho object bên trong

Record không cấm một field trỏ tới List hoặc object mutable. Với danh sách sản phẩm, dùng snapshot bất biến, ví dụ List.copyOf(...) và không mutate dữ liệu trong renderer.

### 5.3. Dữ liệu chung và dữ liệu riêng

Có thể phân loại:

- **Chung:** tiêu đề chiến dịch, announcement công khai, thông tin hỗ trợ chung.
- **Riêng:** tên, địa chỉ email, mã đơn hàng, số tiền, token, locale hoặc branding tenant.

Phân loại này quyết định phần nào có thể dùng chung giữa các người nhận.

## 6. Cấu hình Thymeleaf engine dùng lại và cache parsed template

Một cấu hình minh họa cho Spring Framework với Thymeleaf:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;
import org.thymeleaf.templatemode.TemplateMode;

@Configuration
public class MailTemplateConfiguration {

    @Bean("mailTemplateEngine")
    public SpringTemplateEngine mailTemplateEngine() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();

        resolver.setPrefix("mail-templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(true);

        // Giá trị TTL minh họa, không phải mặc định bắt buộc.
        resolver.setCacheTTLMs(600_000L);

        SpringTemplateEngine engine =
                new SpringTemplateEngine();

        engine.setTemplateResolver(resolver);
        return engine;
    }
}
~~~

Ví dụ file:

~~~text
src/main/resources/
└── mail-templates/
    ├── order-confirmation.html
    ├── password-reset.html
    └── fragments/
        └── footer.html
~~~

### 6.1. Không tạo engine mới trong mỗi lần gửi

Không nên:

~~~java
for (OrderMailView view : allViews) {
    SpringTemplateEngine engine =
            new SpringTemplateEngine();

    // Cấu hình engine/resolver rồi render mỗi email.
}
~~~

Việc tạo engine liên tục có thể bỏ lỡ cache và tăng overhead. Nên reuse một engine đã được cấu hình qua Spring bean.

### 6.2. Dùng Context mới cho mỗi lần render

Engine cấu hình xong có thể dùng chung giữa các lời gọi. Nhưng **Context chứa biến của recipient là mutable**, không nên dùng chung làm singleton hoặc sửa đồng thời từ nhiều thread.

### 6.3. Không nhầm cache parser với output cache

Kể cả khi setCacheable(true), mỗi process với dữ liệu khác vẫn render output tương ứng. Nếu mục tiêu là giảm số process gọi lại cùng dữ liệu, cần thay đổi orchestration của ứng dụng.

### 6.4. Tránh xung đột cấu hình Thymeleaf web

Nếu Spring Boot đã auto-configure một Thymeleaf engine cho web views, hãy sử dụng bean có tên/qualifier phù hợp để tách template email. Không thay đổi ngẫu nhiên resolver dùng cho web và mail trong production.

## 7. Ví dụ template HTML có dữ liệu động

File **mail-templates/order-confirmation.html**:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Xác nhận đơn hàng</title>
</head>
<body>
    <h1>Xác nhận đơn hàng</h1>

    <p>
        Xin chào
        <strong th:text="${customerName}">Khách hàng</strong>,
    </p>

    <p>
        Đơn hàng
        <strong th:text="${orderNumber}">ORDER-001</strong>
        đã được xác nhận.
    </p>

    <p>
        Tổng tiền:
        <strong th:text="${formattedTotal}">500000 VND</strong>
    </p>

    <p>Trân trọng, đội ngũ bán hàng.</p>
</body>
</html>
~~~

Với resolver ở ví dụ trước, gọi:

~~~java
engine.process("order-confirmation", context);
~~~

để tạo HTML.

### 7.1. th:text giúp escape dữ liệu

Với dữ liệu do người dùng hoặc hệ thống bên ngoài cung cấp, **th:text** thực hiện escaping phù hợp với text context trong HTML. Tránh dùng **th:utext** cho dữ liệu không tin cậy.

Việc cache HTML sau render **không tự biến dữ liệu nguy hiểm thành an toàn**. Quy tắc escaping và validation vẫn phải được duy trì.

### 7.2. Tên template cũng là một phần của hợp đồng

Nếu template bị đổi tên hoặc thiếu trong classpath, render có thể lỗi. Đây là lỗi chuẩn bị message, không phải lỗi SMTP.

## 8. Thiết kế RenderedMail để dùng lại output

Kết quả render:

~~~java
public record RenderedMail(
        String subject,
        String plainText,
        String html
) {}
~~~

Renderer:

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

public final class OrderMailRenderer {

    private final TemplateEngine templateEngine;

    public OrderMailRenderer(TemplateEngine templateEngine) {
        this.templateEngine =
                Objects.requireNonNull(templateEngine);
    }

    public RenderedMail render(OrderMailView view) {
        Objects.requireNonNull(view, "view");

        String customerName =
                Objects.requireNonNull(view.customerName());
        String orderNumber =
                Objects.requireNonNull(view.orderNumber());
        BigDecimal total =
                Objects.requireNonNull(view.totalAmount());
        Locale locale =
                Objects.requireNonNull(view.locale());

        String formattedTotal =
                total.toPlainString() + " VND";

        String subject =
                "Xác nhận đơn hàng " + orderNumber;

        Context context = new Context(locale);
        context.setVariable("customerName", customerName);
        context.setVariable("orderNumber", orderNumber);
        context.setVariable("formattedTotal", formattedTotal);

        String html = templateEngine.process(
                "order-confirmation",
                context
        );

        String plainText =
                "Xin chào " + customerName + ",\n\n"
              + "Đơn hàng " + orderNumber
              + " đã được xác nhận.\n"
              + "Tổng tiền: " + formattedTotal + ".\n\n"
              + "Trân trọng, đội ngũ bán hàng.";

        return new RenderedMail(
                subject,
                plainText,
                html
        );
    }
}
~~~

### 8.1. Một lần Thymeleaf process cho một HTML

Trong ví dụ, renderer chỉ gọi templateEngine.process một lần. Plain text được tạo từ cùng DTO bằng formatter đơn giản. Subject, HTML và plain text cùng sử dụng orderNumber và formattedTotal đã được chuẩn bị.

### 8.2. Nếu plain text cũng cần template

Có thể dùng một text template riêng để đảm bảo formatting. Khi đó hai process (một HTML, một text) là chi phí hợp lệ. Điều cần tránh là render **cùng một phiên bản HTML hai lần** chỉ để lấy dữ liệu lặp.

### 8.3. Không dựa vào locale hệ thống bất định

Context nhận Locale rõ ràng. Nếu cần format ngày/tiền phức tạp, hãy chuẩn bị dữ liệu format với locale xác định để output không thay đổi theo default locale của node.

### 8.4. Đây là content snapshot

Object RenderedMail chứa strings đã được tạo. Nếu được lưu qua retry, cần thêm quy định về template version, TTL, nội dung lỗi thời và bảo vệ dữ liệu.

## 9. Dùng output đã render để tạo MimeMessage

Service:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class OrderMailDeliveryService {

    private final OrderMailRenderer renderer;
    private final JavaMailSender sender;

    public OrderMailDeliveryService(
            OrderMailRenderer renderer,
            JavaMailSender sender
    ) {
        this.renderer = renderer;
        this.sender = sender;
    }

    public void send(OrderMailView view) {
        RenderedMail content = renderer.render(view);

        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            false,
                            "UTF-8"
                    );

            helper.setFrom("orders@example.org");
            helper.setTo(view.recipient());
            helper.setSubject(content.subject());

            helper.setText(
                    content.plainText(),
                    content.html()
            );
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Cannot prepare MIME content",
                    ex
            );
        }

        sender.send(message);
    }
}
~~~

**Chỉ một lời gọi renderer.render(view)** phục vụ Subject, plain text và HTML của message.

### 9.1. Anti-pattern dễ gặp

~~~java
String html = renderer.render(view).html();
String plainText = renderer.render(view).plainText();

helper.setText(plainText, html);
~~~

Đây là hai lần render cùng view. Ngoài CPU lặp, chúng có thể tạo output khác nhau nếu renderer phụ thuộc dữ liệu động, thời gian hoặc token.

Nên:

~~~java
RenderedMail content = renderer.render(view);

helper.setText(
        content.plainText(),
        content.html()
);
~~~

### 9.2. Không gửi thẳng HTML cho nhiều recipient khi chưa xem quyền riêng tư

Đối tượng nội dung được render cho một view không nên được dùng chung một cách tùy tiện. Nếu email có tên, số tiền hoặc mã đơn hàng thì mỗi recipient/event cần nội dung riêng.

## 10. HTML và plain text: giảm lặp nhưng giữ đúng nội dung

Một email multipart/alternative có thể chứa text/plain và text/html. Chúng phục vụ những email client và trường hợp accessibility khác nhau.

Có ba cách triển khai:

| Phương án | Chi phí | Lưu ý |
| --- | --- | --- |
| HTML template + plain-text formatter từ view model | 1 lượt render HTML | Bảo đảm hai phần chứa cùng thông tin |
| Hai template HTML và TXT độc lập | 2 lượt render theo format | Cần kiểm thử tính nhất quán |
| Canonical content model + hai renderer | Phụ thuộc kiến trúc | Rõ semantics nhưng phức tạp hơn |

### 10.1. Không bỏ text/plain chỉ để tiết kiệm một lượt render

Nếu nghiệp vụ cần phần văn bản thuần, hãy giữ nó. Một tối ưu CPU không nên làm email khó đọc hoặc giảm khả năng tương thích client.

### 10.2. Không strip HTML bằng regex thô

Việc xóa tag bằng regex có thể làm mất link, bảng, danh sách hoặc line breaks. Nếu sinh plain text từ HTML, nên có bộ chuyển đổi hiểu cấu trúc hoặc một template text được kiểm thử.

### 10.3. Dùng chung view model

Ngay cả khi có hai template, hãy cung cấp cùng dữ liệu đã chuẩn bị thay vì hai nơi độc lập truy vấn và format. Điều này giảm lệch thông tin giữa HTML và plain text.

## 11. Đừng render trước khi xác định có cần gửi

Một tối ưu đơn giản là **bỏ hẳn render đối với mail event không đủ điều kiện**.

Luồng lãng phí:

~~~text
Load data
    |
    v
Render HTML
    |
    v
Check unsubscribe/suppression
    |
    +-- Recipient not eligible -> discard rendered output
~~~

Luồng phù hợp hơn:

~~~text
Validate event and recipient
    |
    v
Check eligibility / preferences / suppression
    |
    +-- Not eligible -> stop
    |
    v
Load view model
    |
    v
Render and send
~~~

### 11.1. Điều kiện có thể kiểm tra trước

- Event bị trùng và đã được xử lý.
- Recipient không có địa chỉ hợp lệ.
- Người dùng đã unsubscribe email marketing.
- Mail nằm trong suppression list.
- Token hoặc notification deadline đã hết hạn.
- Tenant không bật loại thông báo.
- Business state không còn yêu cầu gửi.
- Sender account bị tạm dừng do lỗi cấu hình.

### 11.2. Một số điều kiện cần recheck trước send

Nếu sự kiện nằm trong outbox nhiều giờ, preference hoặc quyền nhận có thể thay đổi. Với loại email cần tuân thủ unsubscribe, worker nên kiểm tra eligibility hiện tại trước gửi, không dựa vào một check đã cũ.

### 11.3. Không render để quyết định eligibility

Hạn chế viết template expression có logic “nếu người dùng không được nhận thì render rỗng”. Quyết định có gửi hay không nên là trách nhiệm domain/service, không phải do kết quả HTML rỗng.

## 12. Fan-out nhiều recipient: chỉ dùng chung nội dung thật sự chung

Một chiến dịch gửi tới nhiều người có thể thuộc hai nhóm.

### 12.1. Nội dung hoàn toàn giống nhau

Một thông báo công khai, không chứa tên người dùng, đơn hàng, token hoặc link unsubscribe riêng, có thể render chung body một lần cho mỗi biến thể hợp lệ:

~~~text
Public content + templateVersion + locale
                   |
                   v
             Render once
                   |
                   +-- Recipient A: own MIME/envelope
                   +-- Recipient B: own MIME/envelope
                   +-- Recipient C: own MIME/envelope
~~~

Vẫn nên dựng message/envelope riêng nếu cần bảo vệ danh sách địa chỉ, theo dõi kết quả từng recipient và retry độc lập.

### 12.2. Nội dung cá nhân hóa

~~~text
Recipient A + View A -> HTML A
Recipient B + View B -> HTML B
Recipient C + View C -> HTML C
~~~

Không được tái sử dụng HTML A cho B chỉ vì template cùng tên.

### 12.3. Kiểm tra mọi nguồn cá nhân hóa

Ngay cả email có body chung cũng có thể có:

- Lời chào theo tên.
- Footer theo tenant.
- URL unsubscribe riêng.
- Tracking link theo recipient.
- Discount code riêng.
- Ngôn ngữ/locale khác nhau.
- Đường dẫn hỗ trợ theo nhóm khách hàng.

Nếu bất kỳ thành phần nào khác nhau, output cache phải có phạm vi phù hợp hoặc nên render độc lập.

### 12.4. Tránh gửi một message với To/CC hàng loạt

Dùng chung body không có nghĩa phải gửi một MIME message hiển thị danh sách người nhận. Gửi hàng loạt trong To/CC có thể làm lộ địa chỉ. Tối ưu render và tối ưu SMTP batching là hai bài toán khác nhau.

## 13. Fragments dùng chung: parse cache và output cache

Thymeleaf hỗ trợ fragments cho header, footer và layout:

~~~html
<div th:replace="~{fragments/common :: header}"></div>

<p th:text="${messageText}">Nội dung</p>

<div th:replace="~{fragments/common :: footer}"></div>
~~~

Dùng fragment giúp bảo trì template, còn cache parser giúp tránh parse file fragment quá nhiều. **Không có nghĩa fragment output mặc định chỉ được render một lần cho mọi email**.

### 13.1. Khi có thể cache output fragment

Fragment phải thật sự bất biến trong scope cache:

- Không chứa recipient-specific data.
- Không chứa token hoặc thời điểm động.
- Không phụ thuộc tenant, hoặc key có tenant.
- Không phụ thuộc locale, hoặc key có locale.
- Có phiên bản/invalidation khi nội dung thay đổi.

### 13.2. Khi không nên

Không cache chung footer chứa unsubscribe link riêng, header theo branding của từng tenant hoặc thông điệp chỉ người dùng có quyền mới được xem.

### 13.3. Ưu tiên engine parser cache trước

Nếu chưa có bằng chứng chi phí xử lý fragment rất lớn, tái sử dụng engine và cache template đã parse thường đơn giản hơn xây một distributed fragment-output cache.

## 14. Memoization trong phạm vi một request/worker attempt

Một cách hiệu quả và ít rủi ro:

~~~java
RenderedMail rendered = renderer.render(view);

MimeMessage message = mimeFactory.build(
        recipient,
        rendered
);

sender.send(message);
~~~

Các lời gọi minh họa trong code được dùng để giải thích luồng dữ liệu; **mimeFactory** là thành phần của ứng dụng.

Một biến local thường có ưu điểm:

- Không cần TTL hoặc eviction.
- Không dùng chung giữa recipient.
- Không cần distributed synchronization.
- Không giữ PII ngoài thời gian xử lý.
- Dễ kiểm thử và truy vết.

### 14.1. Khi nào local object chưa đủ?

Nếu worker gửi thất bại rồi retry ở process khác, RenderedMail không còn trong bộ nhớ. Muốn tái sử dụng qua restart cần lưu snapshot hoặc rendered content một cách bền vững.

### 14.2. Không dùng static Map không giới hạn

Một global cache giữ HTML cá nhân hóa có thể tạo memory leak, stale content hoặc data leakage. Nếu thật sự cần cache dài hạn, nó cần giới hạn dung lượng, key chuẩn, TTL, eviction, isolation và bảo vệ dữ liệu.

## 15. Cache key cho rendered output phải đầy đủ

Nếu cache output bên ngoài một workflow, những yếu tố ảnh hưởng tới nội dung có thể gồm:

~~~text
templateId
templateVersion
locale
tenantId / brand
mailKind
businessEventId
recipient / personalizationScope
viewDataVersion or digest
featureFlagsVersion
~~~

Không có cache key chung cho mọi email. Phải xác định tất cả biến mà template hoặc formatter thật sự sử dụng.

### 15.1. Key chỉ theo templateId là nguy hiểm

Cùng order-confirmation nhưng người nhận khác tên và đơn hàng khác tiền. Nếu cache theo templateId, email của khách A có thể bị gửi cho khách B.

### 15.2. Key chỉ theo recipient cũng chưa đủ

Cùng một người có nhiều đơn hàng, mã OTP khác nhau hoặc nhiều sự kiện thay đổi mật khẩu. Key phải phân biệt ý định gửi và dữ liệu của từng lần.

### 15.3. Template version ngăn stale output

Nếu bản template v5 đã thay phần nội dung pháp lý, một cache cũ theo v4 không tự đổi. Cần version hóa hoặc invalidation rõ ràng.

### 15.4. Tenant và locale không thể bỏ qua

Một email cho tenant A có thể mang logo, địa chỉ hỗ trợ hoặc chính sách khác tenant B. Locale quyết định bản dịch và định dạng. Dùng chung output vượt scope có thể là sự cố riêng tư và nghiệp vụ.

### 15.5. Hash key không bảo vệ value

Dù dùng hash/HMAC để tránh đặt email đầy đủ trong key, bản HTML lưu trong cache vẫn có thể chứa PII, token hoặc số tiền. Phải quản lý access control và encryption/retention cho chính output.

## 16. TTL, invalidation và dữ liệu nhạy cảm

Một output cache dài hạn cần chính sách vòng đời.

| Câu hỏi | Lý do |
| --- | --- |
| Cache giữ bao lâu? | Tránh stale data và lưu PII quá hạn |
| Template đổi thì sao? | Version/invalidate |
| Data nghiệp vụ đổi thì sao? | Snapshot hay refresh |
| Recipient hủy đăng ký? | Recheck eligibility |
| Token hết hạn? | Không gửi link vô dụng |
| Cache đầy? | Eviction và memory limits |
| Cache chung nhiều tenant? | Isolation |
| Log/export cache? | Privacy và secret exposure |
| Node restart? | Local cache mất, distributed cache còn |

### 16.1. Không cache OTP hoặc reset link vô thời hạn

Email reset password thường chứa token có hạn. Rendered HTML cũ có thể hết hiệu lực. Việc tạo token mới cần logic nghiệp vụ riêng và có thể yêu cầu **mail event mới**, không phải template tự tạo một token bất kỳ mỗi lần process.

### 16.2. Redis không tự là giải pháp nhanh hơn

Một lượt cache lookup qua mạng có thể tốn thời gian ngang hoặc hơn một render nhỏ. Distributed cache còn tạo chi phí serialization, invalidation, bảo mật và vận hành. Chỉ thêm khi số liệu cho thấy lợi ích.

### 16.3. Không cache lỗi như output thành công

Nếu template bị thiếu hoặc expression lỗi, không lưu chuỗi rỗng vào cache để các retry sau gửi một email thiếu nội dung. Đánh dấu render failure rõ ràng.

## 17. Outbox: nên lưu DTO snapshot hay HTML đã render?

Với transactional outbox, tác vụ gửi có thể retry sau vài giây, vài phút hoặc được node khác xử lý sau restart.

Hai cách chính:

| Cách | Lưu trong outbox | Khi retry | Ưu/nhược |
| --- | --- | --- | --- |
| **View model snapshot** | Các biến cần cho template và template version | Render lại | Ít lưu HTML, nhưng CPU lặp |
| **Rendered content snapshot** | Subject/plain/html và metadata | Dùng lại | Ít render, nhưng cần bảo vệ PII và freshness |
| **Kết hợp** | View snapshot + rendered content có trạng thái | Tái sử dụng khi hợp lệ | Nhiều trạng thái và chính sách hơn |

### 17.1. Lưu view model, render ở worker

~~~text
Business transaction
    |
    +-- Commit business change
    +-- Insert mail outbox with view snapshot
    |
    v
Worker
    |
    +-- Render
    +-- Build MimeMessage
    +-- Send
~~~

Ưu điểm: không phải render trong transaction nghiệp vụ; output có thể theo template version mong muốn. Nhưng retry có thể phải render thêm nếu không có content cache.

### 17.2. Lưu rendered content sau khi render lần đầu

~~~text
Outbox PENDING
    |
    v
Worker loads view snapshot
    |
    v
Render once
    |
    v
Persist subject/plain/html safely
    |
    v
SMTP attempt 1
    |
    +-- Temporary failure
    |
    v
SMTP attempt 2 reuses persisted content
~~~

Nếu persisted output còn hợp lệ theo policy, retry không cần render lại.

### 17.3. Cần lưu an toàn

Rendered content có thể chứa thông tin khách hàng, số tiền hoặc link riêng. Phải quản lý tenant isolation, phân quyền, encryption at rest khi phù hợp, retention, audit và không log full HTML.

### 17.4. Crash trước khi persist vẫn có thể render lại

Nếu worker render xong rồi crash trước khi lưu output, lần retry có thể render lại. Không thể tuyên bố render exactly once trong mọi failure window chỉ nhờ outbox.

## 18. Render-once không bảo đảm send-once

Ví dụ:

~~~text
Render HTML
    |
    v
Persist HTML
    |
    v
SMTP server accepts message
    |
    v
Worker crashes before status update
    |
    v
Retry sends same HTML again
~~~

Ở đây chỉ render một lần nhưng message có thể gửi hai lần.

Cần phân biệt:

- **Render reuse:** tránh công việc template lặp.
- **Outbox:** giữ ý định gửi bền vững.
- **Claim/lease:** điều phối worker.
- **Idempotency:** giảm tạo nhiều ý định gửi cho cùng sự kiện.
- **Retry:** phục hồi lỗi tạm thời.
- **Unknown outcome handling:** xử lý trường hợp SMTP có thể đã chấp nhận message.

SMTP thông thường không cung cấp bảo đảm exactly-once delivery tổng quát. Cache HTML không phải công cụ loại bỏ toàn bộ duplicate email.

## 19. Khi nào phải render lại?

Một số lý do hợp lệ:

1. Bản template thay đổi và chính sách yêu cầu gửi bản mới.
2. Dữ liệu nghiệp vụ phải phản ánh trạng thái hiện tại.
3. Recipient/tenant/locale hoặc branding thay đổi.
4. Người nhận mất quyền nhận nội dung.
5. Token hoặc link đã hết hạn.
6. Output trước bị sai hoặc thiếu thông tin.
7. Thay đổi quy định/nội dung pháp lý bắt buộc.
8. Worker sử dụng snapshot version không còn được phép.
9. Feature flag thay đổi semantics của message.
10. Mail event mới được tạo cho một nghiệp vụ mới.

### 19.1. Snapshot content và live content

**Snapshot:** nội dung phản ánh một sự kiện đã xảy ra, chẳng hạn hóa đơn đã phát hành. Retry thường cần giữ nguyên.

**Live:** nội dung phải phản ánh trạng thái tại thời điểm gửi. Có thể cần render lại nếu tác vụ bị trễ.

Cần quyết định theo từng loại email, không để cache tự chọn.

### 19.2. Tránh tạo token trực tiếp trong template

Nếu template expression tạo OTP/magic link mới mỗi lần process, retry có thể làm token thay đổi hoặc tạo thêm credential ngoài ý muốn. Hãy tạo token ở tầng nghiệp vụ có policy riêng rồi đưa vào view model.

### 19.3. Tránh thời gian hiện tại không kiểm soát

Nếu template tự gọi thời gian hiện tại, output giữa hai lần render có thể khác. Với email sự kiện, truyền Instant xác định vào view model để giữ tính nhất quán.

## 20. Concurrency và cache stampede

Một output cache tự xây dựng có thể gặp:

~~~text
Worker A -> cache miss -> render
Worker B -> cache miss -> render
Worker C -> cache miss -> render
~~~

Nếu tất cả dùng cùng key an toàn, cơ chế single-flight theo key hoặc compute-if-absent có thể giúp giảm render lặp.

Nhưng cần kiểm soát:

- Bounded cache và TTL.
- Không đặt một global lock cho mọi template.
- Không giữ lock trong khi gọi database/network lâu.
- Không cache exception vĩnh viễn.
- Không chia sẻ output cá nhân hóa sai scope.
- Không để một key lỗi làm chặn toàn bộ worker.
- Không giả định local cache giải quyết duplicate giữa các node.

### 20.1. Đừng tối ưu sớm bằng distributed lock

Với phần lớn email có nội dung riêng, mỗi event thực sự cần một render. Distributed lock không giúp giảm số render cần thiết mà có thể làm giảm throughput.

### 20.2. TemplateEngine dùng chung nhưng Context không dùng chung

Dùng Spring bean engine đã cấu hình, tạo **Context mới trong mỗi render**. Không giữ Context mutable và thay đổi customerName theo từng request đồng thời.

## 21. Resource và attachment là bài toán hiệu năng khác

Một email có PDF hoặc inline image:

~~~java
helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf"
);

helper.addInline(
        "companyLogo",
        logoResource,
        "image/png"
);
~~~

Các thao tác này liên quan MIME resource. Một số resource có thể được đọc muộn khi Jakarta Mail serialize message trong JavaMailSender.send.

Giảm một lượt render HTML không làm PDF tự tải nhanh hơn.

### 21.1. Đo các bước riêng

Các metric có thể cần:

~~~text
mail.template.render.duration
mail.attachment.generate.duration
mail.resource.load.duration
mail.message.build.duration
mail.smtp.submit.call.duration
~~~

### 21.2. Đừng serialize MIME hai lần chỉ để đo

Gọi message.writeTo(...) một lần để đo rồi để JavaMailSender thực hiện lại có thể nhân đôi I/O và CPU. Dùng instrumentation phù hợp với thao tác vốn có thay vì thêm công việc đắt đỏ.

### 21.3. Cache attachment cũng có rủi ro

Nếu lưu byte[] PDF cho retry, cần giới hạn kích thước, retention, quyền truy cập và tính toàn vẹn. Cache HTML và cache PDF phục vụ các mục tiêu khác nhau.

## 22. Đo số render để biết tối ưu có tác dụng

Các metric gợi ý:

| Metric | Ý nghĩa |
| --- | --- |
| **mail.template.render.invocations** | Số lượt gọi process |
| **mail.template.render.duration** | Thời gian mỗi lượt render |
| **mail.template.render.failures** | Số lỗi render |
| **mail.template.output.reuse** | Số lần dùng lại output |
| **mail.template.output.cache.hit** | Cache hits |
| **mail.template.output.cache.miss** | Cache misses |
| **mail.event.created** | Số ý định gửi |
| **mail.smtp.submit.attempts** | Số lần thử gửi |
| **mail.outbox.pending** | Backlog |

### 22.1. Render invocations per event

Nếu một email dùng duy nhất HTML template nhưng metric báo 3 lượt render/event, cần xem có render preview, validation, build hoặc retry thừa không.

Nếu một mail dùng HTML và text template riêng, 2 lượt có thể là đúng. Không áp cùng một target cho mọi loại message.

### 22.2. Phân biệt purpose

Có thể phân nhóm:

~~~text
purpose=preview
purpose=delivery
purpose=retry
~~~

Preview do người dùng chủ động yêu cầu không nhất thiết là render lãng phí.

### 22.3. Đếm cache hits chưa đủ

Một output cache có hit rate cao nhưng network lookup chậm, dữ liệu quá lớn hoặc invalidate phức tạp có thể không tăng hiệu năng toàn hệ thống. Phải so sánh CPU, memory, render duration, send latency và vận hành.

## 23. Instrument Thymeleaf renderer bằng Micrometer

Một adapter đo Timer và Counter:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.IContext;

public final class ObservedHtmlRenderer {

    private final TemplateEngine engine;
    private final MeterRegistry registry;

    public ObservedHtmlRenderer(
            TemplateEngine engine,
            MeterRegistry registry
    ) {
        this.engine = engine;
        this.registry = registry;
    }

    public String render(
            String template,
            IContext context,
            String kind
    ) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return engine.process(template, context);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.template.render.duration",
                            "kind", kind,
                            "outcome", outcome
                    )
            );

            registry.counter(
                    "mail.template.render.invocations",
                    "kind", kind,
                    "outcome", outcome
            ).increment();
        }
    }
}
~~~

### 23.1. Ghi cả lỗi

Các phép đo nằm trong finally nên một render lỗi vẫn được tính. Nếu chỉ đo thành công, dashboard sẽ bỏ qua những render thất bại vì dữ liệu/template.

### 23.2. Kiểm soát cardinality

**kind** phải lấy từ tập tên loại email hữu hạn. Không đưa recipient, orderId, eventId hoặc chuỗi template tùy ý do người dùng cung cấp vào metric tags.

### 23.3. Không log full HTML

Nếu cần chẩn đoán, lưu correlation ID, kind, template version, duration và error category. Rendered HTML có thể chứa PII, token hoặc thông tin giao dịch.

### 23.4. Không cộng hai Timer chồng lấn

Nếu có một Timer bao toàn bộ mail preparation và Timer con cho render, không cộng duration của chúng rồi gọi đó là tổng chuẩn bị. Timer cha đã bao gồm timer con.

## 24. So sánh trước và sau tối ưu

| Chỉ số | Điều cần đánh giá |
| --- | --- |
| Số lượt render/event | Có giảm lượt thừa? |
| Tổng render CPU time | Chi phí CPU thực tế giảm không? |
| Render p50/p95/p99 | Độ trễ từng lượt thay đổi thế nào? |
| Worker CPU và allocation | Bộ nhớ/GC cải thiện không? |
| Queue delay | Worker xử lý nhanh hơn không? |
| Event-to-relay acceptance | Người dùng có lợi ích không? |
| Cache lookup latency | Có bù mất lợi ích render không? |
| Error ratio | Có lỗi mới không? |
| Stale/misrouted content incidents | Có giữ an toàn dữ liệu không? |

### 24.1. p95 từng lượt có thể không giảm

Nếu một render vẫn mất 10 ms nhưng giảm từ 3 lượt xuống 1, p95 render vẫn gần 10 ms, trong khi tổng CPU cho template có thể giảm đáng kể.

### 24.2. End-to-end có thể không đổi

Nếu SMTP và queue chiếm gần hết thời gian, tối ưu render có thể chưa làm người dùng nhận email nhanh hơn đáng kể. Dù vậy, nó có thể tăng capacity và giảm chi phí khi traffic cao.

### 24.3. Chỉ tối ưu khi có baseline

Trước khi xây Redis cache hoặc distributed lock, hãy đo số process, duration, CPU, load và lỗi, rồi kiểm tra lại theo cùng điều kiện tải.

## 25. Unit test kiểm tra render đúng một lần

Mockito có thể kiểm tra orchestration mà không cần SMTP thật:

~~~java
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Locale;
import java.util.Properties;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.IContext;

class OrderMailDeliveryServiceTest {

    @Test
    void rendersHtmlOnceBeforeSending() {
        TemplateEngine engine = mock(TemplateEngine.class);

        when(engine.process(
                eq("order-confirmation"),
                any(IContext.class)
        )).thenReturn("<p>Đơn hàng đã xác nhận.</p>");

        OrderMailRenderer renderer =
                new OrderMailRenderer(engine);

        JavaMailSender sender =
                mock(JavaMailSender.class);

        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage())
                .thenReturn(message);

        OrderMailView view = new OrderMailView(
                "event-1001",
                "an@example.net",
                "Nguyễn An",
                "ORDER-1001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z"),
                Locale.forLanguageTag("vi-VN")
        );

        OrderMailDeliveryService service =
                new OrderMailDeliveryService(renderer, sender);

        service.send(view);

        verify(engine, times(1)).process(
                eq("order-confirmation"),
                any(IContext.class)
        );

        verify(sender, times(1))
                .send(any(MimeMessage.class));
    }
}
~~~

### 25.1. Test đang chứng minh điều gì?

Với một lần gọi service, engine.process cho HTML được gọi một lần và sender.send được gọi một lần. Mockito không tạo kết nối SMTP.

### 25.2. Test nội dung riêng

Vì engine trong test là mock, test trên **không chứng minh** HTML thực tế đúng. Cần một test riêng dùng template thật, dữ liệu giả và kiểm tra escaping, locale, subject và text/plain.

### 25.3. Test input không đủ điều kiện không render

Nếu service có eligibility check trước renderer:

~~~java
verifyNoInteractions(engine);
verify(sender, never()).send(any(MimeMessage.class));
~~~

là những assertion hữu ích cho event không đủ điều kiện gửi.

## 26. Test không trộn nội dung giữa người nhận

Một test đặc biệt quan trọng khi dùng output cache:

~~~java
String htmlA = renderer.render(viewA).html();
String htmlB = renderer.render(viewB).html();

assertTrue(htmlA.contains("ORDER-A"));
assertFalse(htmlA.contains("ORDER-B"));

assertTrue(htmlB.contains("ORDER-B"));
assertFalse(htmlB.contains("ORDER-A"));
~~~

Đoạn này minh họa các assertion khi **viewA/viewB** là fixture độc lập và renderer dùng template thật. Nó nhằm bảo vệ khỏi cache key thiếu dữ liệu hoặc Context bị dùng chung.

Các tình huống cần phủ:

- Recipient A/B có tên và đơn hàng khác nhau.
- Cùng recipient nhưng event khác nhau.
- Hai tenant cùng template name.
- Hai locale khác nhau.
- Template v4 và v5.
- Nhiều worker gọi render đồng thời.
- Token/signed URL khác nhau.
- Cache entry hết hạn hoặc bị invalidate.

**Không được coi giảm render count là thành công nếu output của khách hàng bị lẫn nhau.**

## 27. Test retry và trạng thái output snapshot

Một ma trận kiểm thử outbox:

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Chưa có output snapshot | Render và lưu nếu policy yêu cầu |
| Retry SMTP 421 với snapshot hợp lệ | Tái sử dụng output |
| Worker restart | Đọc output bền vững nếu đã persist |
| Render thất bại | Không gửi SMTP, ghi lỗi preparation |
| Recipient thay đổi | Không reuse sai recipient |
| Template version đổi | Dùng snapshot cũ hoặc regenerate theo policy |
| Token hết hạn | Không phát lại link không còn hợp lệ |
| Duplicate event | Hạn chế tạo job/render trùng |
| Crash trước persist | Cho phép render lại an toàn |
| Crash sau SMTP accept | Theo dõi nguy cơ gửi trùng |

Không kiểm thử SMTP bằng việc gửi email thật ra Internet khi mục tiêu chỉ là logic reuse. Có thể dùng fake repository/outbox và mock JavaMailSender.

## 28. Một số anti-pattern cần tránh

| Anti-pattern | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Tạo Thymeleaf engine cho từng email | Không tận dụng cache engine | Reuse bean đã cấu hình |
| Render trong controller và worker | Lặp công việc | Một nơi render, truyền kết quả |
| Render hai lần lấy HTML và plain | Gọi thừa | RenderedMail object |
| Render trước unsubscribe check | Tốn CPU vô ích | Eligibility trước |
| Global cache theo templateId | Rò rỉ cá nhân hóa | Scope/key đầy đủ |
| Cache theo recipientId duy nhất | Lẫn sự kiện khác nhau | Event/version/data key |
| Cache HTML chứa OTP vô hạn | Token hết hạn, lộ PII | TTL và domain policy |
| Dùng chung mutable Context | Lẫn dữ liệu đồng thời | Context mới mỗi render |
| Template tự query DB | N+1, snapshot bất định | DTO sẵn dữ liệu |
| Dùng chung output nhiều tenant | Sai branding, riêng tư | Tenant-aware isolation |
| Render mỗi retry không cần thiết | CPU và nội dung biến động | Snapshot/persist hợp lệ |
| Tưởng cache parsed template là output reuse | Hiểu sai | Đo process invocations |
| Bỏ plain text để giảm CPU | Mất khả năng tương thích | Text formatter/template |
| Cache mà không đo hiệu quả | Tăng độ phức tạp | Baseline, compare |
| Coi render-once là gửi đúng một lần | SMTP vẫn có duplicate window | Outbox, idempotency, review |
| Dùng eventId làm metric tag | High cardinality | Correlation ID trong log |

## 29. Câu hỏi thường gặp

**1. Bật cache Thymeleaf có làm process chỉ chạy một lần không?**

Không. Cache thường giúp tái sử dụng template đã parse; mỗi process với Context vẫn sinh output. Muốn giảm số process phải thay đổi luồng gọi hoặc tái sử dụng output đúng phạm vi.

**2. Có nên cache mọi HTML email không?**

Không. HTML có thể chứa PII, token, số tiền và nội dung cũ. Chỉ cache khi đã xác định key, TTL, version, quyền truy cập và chính sách cập nhật.

**3. Một email HTML và plain text có cần hai lượt render không?**

Có thể cần hai nếu chúng là hai template độc lập. Nếu plain text được dựng từ cùng view model bằng formatter, chỉ một lượt HTML process có thể đủ.

**4. Vì sao Context không nên là singleton?**

Context có thể chứa biến của recipient, thường mutable. Chia sẻ giữa nhiều thread có thể làm trộn dữ liệu người dùng.

**5. Gửi một thông báo công khai cho 10.000 người có thể render chung không?**

Có thể nếu nội dung thật sự giống nhau và không có token, unsubscribe link, personalization, locale hoặc branding khác. Vẫn cần bảo vệ envelope recipient và retry riêng khi phù hợp.

**6. Tại sao @Cacheable không phải lựa chọn mặc định?**

Nó yêu cầu key phản ánh mọi dữ liệu ảnh hưởng output và có cơ chế invalidation/TTL. Một cache sai có thể gửi nội dung của A cho B.

**7. Outbox nên lưu dữ liệu hay HTML?**

Tùy nghiệp vụ. Snapshot dữ liệu nhỏ và linh hoạt hơn nhưng có thể render lại. Lưu HTML tránh render retry nhưng có rủi ro lưu PII và stale output. Có thể kết hợp nếu quản lý trạng thái rõ.

**8. Template thay đổi trong thời gian retry thì sao?**

Cần quyết định cố định snapshot version hay dùng version mới. Không để output phụ thuộc ngẫu nhiên node nào đang xử lý.

**9. Render một lần có ngăn gửi email trùng không?**

Không. SMTP có thể accept rồi worker crash trước khi cập nhật trạng thái. Retry có thể gửi trùng dù không render lại.

**10. Khi nào phải render lại?**

Khi template/data/locale/tenant cần thay đổi theo chính sách, output lỗi thời, token hết hạn hoặc business event mới cần thông tin khác.

**11. Có nên dùng regex String.replace để cá nhân hóa HTML chung không?**

Không nên như chiến lược tổng quát. Nó có thể sai escaping và placeholder, gây HTML injection hoặc trộn dữ liệu. Dùng template context đúng hoặc formatter an toàn.

**12. Redis có luôn giúp tăng tốc không?**

Không. Cache lookup có network/serialization overhead. Cần đo chi phí render so với chi phí cache và xét thêm bảo mật/invalidation.

**13. Đếm lượt render bằng gì?**

Instrument TemplateEngine.process trong một adapter tập trung; ghi Counter/Timer với tag kind/outcome/purpose hữu hạn.

**14. Có test render count mà không cần SMTP không?**

Có. Mock TemplateEngine và JavaMailSender, verify process được gọi đúng số lần. Test template thật nên được thực hiện riêng.

**15. Vì sao số render giảm nhưng thời gian gửi không cải thiện nhiều?**

Nếu SMTP connection, attachment, queue hoặc provider đang chiếm phần lớn thời gian, render không phải nút thắt chính.

**16. Có nên thực hiện query trong Thymeleaf expression không?**

Nên tránh khi có thể. Nó làm render khó dự đoán và có thể gây N+1. Chuẩn bị view model trước giúp kiểm soát.

**17. HTML đã render có phải dữ liệu cá nhân không?**

Có thể có. Nếu chứa tên, email, số tiền, mã đơn hàng hoặc token, cần bảo vệ retention, quyền truy cập và xóa theo chính sách.

**18. Có cần cache warming không?**

Chỉ khi cold-start parse gây ảnh hưởng đáng kể. Reuse engine và parsed-template cache thường là bước đầu. Nếu warm-up, dùng dữ liệu giả và không gửi SMTP.

## 30. Ghi nhớ về giảm số lần render template không cần thiết

**Tối ưu render đúng bắt đầu bằng việc đếm số lượt gọi template engine và định nghĩa rõ nội dung nào được phép tái sử dụng.** Trong Spring Framework Mail, hãy tách dữ liệu nghiệp vụ khỏi template, tạo view model rõ ràng, dùng một engine được cấu hình/cache parsed template, và truyền một object **RenderedMail** xuyên suốt bước chuẩn bị MIME thay vì render nhiều lần để lấy Subject, HTML và plain text.

Kiểm tra **eligibility, suppression và validation** trước khi render những email không cần gửi. Khi fan-out, chỉ dùng chung output không cá nhân hóa trong cùng scope template version, locale và tenant; không chia sẻ dữ liệu của recipient A cho B. Với transactional outbox và retry, cân nhắc snapshot view model hoặc persist nội dung đã render, đi kèm TTL, version, access control và chính sách cho token hết hạn.

**Render-once không phải send-once**: lỗi SMTP và crash vẫn có thể tạo duplicate. Hãy đo render invocations, duration, CPU và tác động end-to-end bằng Micrometer; kiểm thử count với Mockito, đồng thời kiểm thử sự riêng tư của output với template thật.

Kết quả mong muốn là **giảm những lượt render thực sự dư thừa** mà vẫn tạo đúng email, đúng người nhận, đúng phiên bản và đúng thời điểm.
