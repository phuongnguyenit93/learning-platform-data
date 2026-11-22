# Tách kiểm thử logic chọn template khỏi kiểm thử transport

Trong một ứng dụng **Spring Framework Mail**, gửi email thường là kết quả của nhiều quyết định và nhiều bước xử lý: hệ thống xác định một sự kiện nghiệp vụ, chọn loại email và ngôn ngữ, chọn template phù hợp, render subject/body, rồi dựng MIME message và gửi bằng `JavaMailSender`. Khi tất cả nằm trong một phương thức, kiểm thử trở nên khó hiểu: muốn xác nhận “đơn hàng được xác nhận dùng đúng template tiếng Việt” lại phải tạo SMTP server giả; còn muốn kiểm tra “email có subject Unicode và body HTML hợp lệ” lại phải dựng đơn hàng, tạo customer và chạy toàn bộ business workflow.

Cách tiếp cận tốt hơn là **tách kiểm thử logic chọn template khỏi kiểm thử transport**. Template selection là quyết định của ứng dụng: dựa trên loại thông báo, ngôn ngữ, trạng thái nghiệp vụ hoặc một biến thể có chủ đích để chọn mẫu nội dung. Transport là trách nhiệm hạ tầng: nhận nội dung đã render, dựng email MIME với To/From/Subject/body/attachment và gọi mail sender. Hai phần có đầu vào, kết quả, rủi ro và kỹ thuật kiểm thử khác nhau.

Mục tiêu không chỉ làm test chạy nhanh. Ranh giới này giúp chúng ta biết chính xác **thay đổi nào làm test thất bại**, tránh gửi mail thật trong unit test, giảm mock không cần thiết và không vô tình để logic chọn template phụ thuộc vào SMTP.

Bài này xây dựng kiến trúc selector → renderer → gateway; trình bày các ví dụ Java, JUnit 5, Mockito và Spring Mail; hướng dẫn thiết kế test data, negative cases, HTML/Unicode, lỗi transport, tích hợp và những bẫy phổ biến.

## 1. Cần phân biệt ba trách nhiệm, không chỉ hai lớp

Một luồng gửi mail có thể gồm:

1. **Chọn template (selection)**: email này phải dùng mẫu nào?
2. **Render template (rendering)**: thay dữ liệu vào mẫu để tạo subject và nội dung gì?
3. **Transport**: gửi nội dung đã render dưới dạng MIME như thế nào?

Ví dụ ứng dụng có ba purpose:

- `ORDER_CONFIRMED`: xác nhận đơn hàng.
- `PASSWORD_RESET`: hướng dẫn đặt lại mật khẩu.
- `INVOICE_READY`: thông báo hóa đơn sẵn sàng.

Khi đơn hàng `ORD-2048` được xác nhận, user muốn nhận thư tiếng Việt:

~~~text
Business event: ORDER_CONFIRMED
Locale: vi-VN
    |
    v
Template selector
    -> order-confirmation/vi-VN/v1
    |
    v
Template renderer
    -> Subject: Đơn hàng ORD-2048 đã được xác nhận
    -> Plain text: Xin chào...
    -> HTML: <p>Xin chào...</p>
    |
    v
Mail transport gateway
    -> To, From, Subject, MIME multipart, UTF-8
    -> JavaMailSender.send(...)
~~~

**Test selector** chỉ nên khẳng định `ORDER_CONFIRMED + vi-VN` chọn `order-confirmation/vi-VN/v1`. Nó không cần biết SMTP host, MIME boundary hoặc `JavaMailSender`.

**Test renderer** khẳng định dữ liệu được thay đúng vào subject/plain text/HTML và escape dữ liệu không đáng tin cậy. Nó không cần gửi SMTP.

**Test transport** khẳng định gateway nhận nội dung hoàn chỉnh thì dựng và gửi MIME đúng, hoặc xử lý lỗi gửi phù hợp. Nó không cần biết đơn hàng đang ở trạng thái nào và tại sao selector chọn template.

## 2. Vì sao một test bao trùm tất cả dễ thất bại?

Giả sử có service như sau:

~~~java
@Service
public class OrderMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final OrderRepository orders;

    public void sendConfirmation(UUID orderId, Locale locale) {
        Order order = orders.findById(orderId)
                .orElseThrow();

        String template = locale.getLanguage().equals("vi")
                ? "mail/order-vi"
                : "mail/order-en";

        // Render template, dựng MimeMessage,
        // set subject, gửi SMTP...
    }
}
~~~

Nếu kiểm thử dùng `@SpringBootTest` và SMTP server giả cho mọi case, một assertion về fallback ngôn ngữ có thể thất bại vì server chưa chạy, TLS bị đổi cấu hình hoặc mock repository sai. Ngược lại, test transport phải biết cách chuẩn bị một order và locale dù transport không quan tâm.

Dấu hiệu cần tách:

- Test selector cần mock `JavaMailSender`.
- Test MIME cần tạo `OrderRepository` và domain event.
- Một lỗi subject Unicode làm hỏng test về locale fallback.
- Test dùng SMTP thật chỉ để xác nhận một enum được ánh xạ thành tên template.
- Mỗi biến thể template tạo thêm một bản test tích hợp chậm.
- Việc đổi nhà cung cấp SMTP khiến các test nghiệp vụ/template phải sửa.

**Nguyên tắc:** Mỗi test nên có một lý do chính để thất bại. Không bắt unit test chọn template đi qua mạng, context Spring hoặc MIME nếu kết quả cần kiểm tra là một quyết định thuần dữ liệu.

## 3. Kiến trúc đề xuất cho Spring Framework Mail

~~~mermaid
flowchart TD
    A["HTTP / Scheduler / Domain event"] --> B["Application handler"]
    B --> C["Authorization + recipient policy"]
    C --> D["Template selector"]
    D --> E["TemplateSelection"]
    E --> F["Template renderer"]
    F --> G["RenderedMail"]
    G --> H["MailGateway interface"]
    H --> I["SpringMailGateway"]
    I --> J["MimeMessageHelper"]
    J --> K["JavaMailSender"]
    K --> L["SMTP relay"]
~~~

Các hợp đồng cần rõ:

| Thành phần | Nhận gì? | Trả gì hoặc làm gì? | Loại test ưu tiên |
| --- | --- | --- | --- |
| Application handler | Business command, actor, entity | Điều phối use case | Unit test tương tác và policy |
| Template selector | Purpose, locale, rule context | Template descriptor | **Unit test thuần** |
| Template renderer | Descriptor và view model | Subject, plain text, HTML | Unit/component test renderer |
| MailGateway | RenderedMail, metadata gửi | Gửi hoặc trả lỗi có phân loại | **Transport unit test** |
| JavaMailSender | MimeMessage/transport config | SMTP send | Test bằng fake, integration SMTP |
| SMTP provider | SMTP session | Acceptance/rejection | Integration contract khi cần |

Đặt interface hạ tầng đúng hướng phụ thuộc: application layer phụ thuộc `MailGateway` abstraction, không phụ thuộc trực tiếp host, port hoặc các chi tiết SMTP.

### Các bài test khác nhau bảo vệ những hợp đồng khác nhau

- **Selector contract:** mỗi purpose và locale ánh xạ tới template hợp lệ.
- **Renderer contract:** dữ liệu được render đúng, an toàn và có đủ nội dung dự phòng.
- **Gateway contract:** MIME hợp lệ, đúng header/recipient/encoding và đúng cách xử lý exception.
- **Wiring contract:** Spring inject đúng implementation, template engine và sender.
- **Provider contract:** cấu hình SMTP/TLS/AUTH hoạt động với server thật hoặc sandbox.

Không nên dùng test cấp cao thay thế tất cả test cấp thấp, cũng không nên kiểm thử lại mọi quy tắc của selector trong test SMTP.

## 4. Thiết kế dữ liệu cho logic chọn template

Đầu tiên biểu diễn **mục đích email** bằng enum do ứng dụng kiểm soát:

~~~java
public enum MailPurpose {
    ORDER_CONFIRMED,
    PASSWORD_RESET,
    INVOICE_READY
}
~~~

Một key định danh phương án chọn:

~~~java
public record TemplateKey(
        MailPurpose purpose,
        String localeTag) {
}
~~~

Một kết quả chọn template:

~~~java
import java.util.Locale;

public record TemplateSelection(
        String templateCode,
        Locale locale,
        int version) {
}
~~~

`templateCode` là một mã nội bộ như `mail/order-confirmation`, không phải path tùy ý do HTTP request gửi vào. `version` mô tả phiên bản template theo quy ước dự án. `locale` là ngôn ngữ mà renderer thực sự sử dụng sau khi selector đã áp dụng fallback.

### Tại sao nên trả descriptor thay vì tên file đơn lẻ?

Nếu selector chỉ trả `String`, người gọi có thể phải tự đoán locale đã được fallback, version hoặc biến thể. Một `TemplateSelection` mang đủ thông tin giúp renderer chỉ tập trung vào render, không phải lặp lại logic chọn.

### Không để selector gửi email

Một selector tốt không nhận `JavaMailSender`, không tạo `MimeMessage` và không gọi SMTP. Phương thức `select(...)` nên là phép tính dựa trên dữ liệu được cung cấp và cấu hình catalog.

## 5. Ví dụ TemplateSelector thuần Java

Dưới đây là implementation nhỏ sử dụng catalog ánh xạ theo purpose và locale. Nó thử đúng locale được yêu cầu, sau đó fallback tới ngôn ngữ mặc định nếu có.

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public final class MailTemplateSelector {

    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private final Map<TemplateKey, TemplateSelection> catalog;

    public MailTemplateSelector(
            Map<TemplateKey, TemplateSelection> catalog) {
        this.catalog = Map.copyOf(catalog);
    }

    public TemplateSelection select(
            MailPurpose purpose,
            Locale requestedLocale) {

        Objects.requireNonNull(purpose, "purpose");

        Locale locale = requestedLocale == null
                ? DEFAULT_LOCALE
                : requestedLocale;

        TemplateKey exact = new TemplateKey(
                purpose,
                locale.toLanguageTag()
        );

        TemplateSelection selected = catalog.get(exact);
        if (selected != null) {
            return selected;
        }

        TemplateKey fallback = new TemplateKey(
                purpose,
                DEFAULT_LOCALE.toLanguageTag()
        );

        selected = catalog.get(fallback);
        if (selected != null) {
            return selected;
        }

        throw new TemplateUnavailableException(
                "Không có template cho " + purpose
        );
    }
}
~~~

`TemplateUnavailableException` là exception do ứng dụng định nghĩa, ví dụ kế thừa `RuntimeException`. `Map.copyOf` tạo một snapshot map không sửa đổi được qua reference này; bản thân các value object bên trong cũng nên có dữ liệu bất biến.

Mã minh họa chỉ dùng exact locale tag và fallback mặc định. Một sản phẩm có thể cần chuỗi fallback phong phú hơn:

~~~text
vi-VN -> vi -> en-US
en-AU -> en -> en-US
fr-CA -> fr -> fr-FR -> en-US
~~~

Không tự áp dụng thứ tự này nếu nghiệp vụ chưa quy định. Test phải phản ánh **chính sách locale chính xác** của ứng dụng.

### Ví dụ catalog

~~~java
Map<TemplateKey, TemplateSelection> catalog =
        Map.of(
                new TemplateKey(
                        MailPurpose.ORDER_CONFIRMED,
                        "vi-VN"
                ),
                new TemplateSelection(
                        "mail/order-confirmed",
                        Locale.forLanguageTag("vi-VN"),
                        1
                ),

                new TemplateKey(
                        MailPurpose.ORDER_CONFIRMED,
                        "en-US"
                ),
                new TemplateSelection(
                        "mail/order-confirmed",
                        Locale.forLanguageTag("en-US"),
                        1
                ),

                new TemplateKey(
                        MailPurpose.PASSWORD_RESET,
                        "vi-VN"
                ),
                new TemplateSelection(
                        "mail/password-reset",
                        Locale.forLanguageTag("vi-VN"),
                        2
                )
        );
~~~

Cùng `templateCode` có thể dùng cho nhiều locale khi renderer tra cứu resource bằng locale; hoặc mỗi locale có mã riêng. Điều quan trọng là hợp đồng giữa selector và renderer phải nhất quán.

## 6. Unit test selector mà không khởi động Spring

Có thể dùng JUnit 5 với constructor trực tiếp:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Locale;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MailTemplateSelectorTest {

    private MailTemplateSelector selector;

    @BeforeEach
    void setUp() {
        Map<TemplateKey, TemplateSelection> catalog =
                Map.of(
                        new TemplateKey(
                                MailPurpose.ORDER_CONFIRMED,
                                "vi-VN"
                        ),
                        new TemplateSelection(
                                "mail/order-confirmed",
                                Locale.forLanguageTag("vi-VN"),
                                1
                        ),

                        new TemplateKey(
                                MailPurpose.ORDER_CONFIRMED,
                                "en-US"
                        ),
                        new TemplateSelection(
                                "mail/order-confirmed",
                                Locale.forLanguageTag("en-US"),
                                1
                        )
                );

        selector = new MailTemplateSelector(catalog);
    }

    @Test
    void selectsVietnameseForVietnameseOrder() {
        TemplateSelection result = selector.select(
                MailPurpose.ORDER_CONFIRMED,
                Locale.forLanguageTag("vi-VN")
        );

        assertEquals(
                "mail/order-confirmed",
                result.templateCode()
        );

        assertEquals(
                "vi-VN",
                result.locale().toLanguageTag()
        );

        assertEquals(1, result.version());
    }

    @Test
    void selectsEnglishWhenEnglishRequested() {
        TemplateSelection result = selector.select(
                MailPurpose.ORDER_CONFIRMED,
                Locale.forLanguageTag("en-US")
        );

        assertEquals(
                "en-US",
                result.locale().toLanguageTag()
        );
    }

    @Test
    void fallsBackWhenLocaleIsNotAvailable() {
        TemplateSelection result = selector.select(
                MailPurpose.ORDER_CONFIRMED,
                Locale.forLanguageTag("ja-JP")
        );

        assertEquals(
                "vi-VN",
                result.locale().toLanguageTag()
        );
    }

    @Test
    void rejectsPurposeWithoutAnyTemplate() {
        assertThrows(
                TemplateUnavailableException.class,
                () -> selector.select(
                        MailPurpose.INVOICE_READY,
                        Locale.forLanguageTag("vi-VN")
                )
        );
    }
}
~~~

Những test này:

- Không cần `@SpringBootTest`.
- Không cần mail server.
- Không mock `JavaMailSender`.
- Không cần Spring context hoặc database.
- Chạy nhanh và tập trung đúng vào quy tắc chọn template.

**Điểm mấu chốt:** test so sánh `TemplateSelection` hoặc các field mang ý nghĩa nghiệp vụ; không so sánh số lần gọi `MimeMessageHelper`.

## 7. Test case selector cần bao phủ những gì?

Các chiều thường gặp:

| Đầu vào/tình huống | Điều cần xác minh |
| --- | --- |
| Purpose hợp lệ, locale có template | Chọn đúng template |
| Locale thiếu bản dịch | Fallback đúng policy |
| Locale null | Dùng locale mặc định hoặc từ chối theo contract |
| Purpose không có template | Báo lỗi tường minh, không chọn bừa |
| Template version khác | Chọn đúng version theo rule |
| Feature flag/variant | Chọn biến thể nhất quán và có căn cứ |
| Tenant hoặc brand khác | Không lấy template của tenant khác |
| Notification type có yêu cầu bảo mật | Không fallback sang marketing template |
| Catalog thiếu key | Fail closed hoặc fallback có quy tắc |
| Hai locale gần nhau | Xử lý ngôn ngữ và vùng theo rule |
| Event không phù hợp | Không chọn template chỉ vì tên gần giống |

Không cần một test tích hợp SMTP cho mọi tổ hợp của bảng này. Viết **parameterized unit tests** nếu có nhiều case tương tự.

### Test parameterized cho locale

~~~java
@ParameterizedTest
@CsvSource({
        "vi-VN,vi-VN",
        "en-US,en-US",
        "ja-JP,vi-VN"
})
void choosesExpectedLocale(
        String requested,
        String expected) {

    TemplateSelection selection = selector.select(
            MailPurpose.ORDER_CONFIRMED,
            Locale.forLanguageTag(requested)
    );

    assertEquals(
            expected,
            selection.locale().toLanguageTag()
    );
}
~~~

Không cần thêm sender mock vào test này. Khi chính sách fallback đổi, chỉ selector test và phần cấu hình catalog liên quan cần được xem xét.

## 8. Đừng để HTTP client tự chọn template tùy ý

Giả sử endpoint nhận:

~~~json
{
  "orderId": "ORD-2048",
  "template": "mail/password-reset"
}
~~~

Nếu application service tin trường `template` trực tiếp, người gọi có thể yêu cầu một template không thuộc use case hoặc khiến nội dung sai. Trong một số hệ thống, việc ghép path template từ input còn tạo nguy cơ path traversal hoặc template injection nếu resource loader và dữ liệu không được kiểm soát.

Cách tốt hơn: command nhận business intent hoặc resource ID:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        UUID actorId) {
}
~~~

Application service xác minh order và actor, rồi chọn:

~~~java
TemplateSelection selection = selector.select(
        MailPurpose.ORDER_CONFIRMED,
        recipientLocale
);
~~~

**Selector test không thay thế authorization test.** Phải kiểm tra riêng rằng người gọi có quyền gửi thông báo và recipient được phép nhận. Nhưng việc chọn `MailPurpose` nên bắt nguồn từ use case được kiểm soát, không từ một giá trị tùy ý để đổi routing hoặc template.

## 9. Tách rendering ra khỏi selection

Selector trả descriptor; renderer nhận descriptor và view model rồi dựng nội dung:

~~~java
public record RenderedMail(
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

~~~java
public interface MailTemplateRenderer {
    RenderedMail render(
            TemplateSelection selection,
            OrderMailViewModel model);
}
~~~

~~~java
public record OrderMailViewModel(
        String recipient,
        String customerName,
        String orderCode) {
}
~~~

Các record nêu trên chỉ là ví dụ dữ liệu cho email xác nhận đơn hàng. Với nhiều loại email, có thể thiết kế hierarchy view model có type riêng cho password reset, invoice và marketing, thay vì ép mọi template nhận cùng một map không có kiểm tra kiểu.

### Renderer cần làm những việc gì?

Tùy template engine và sản phẩm:

- Load template đúng `templateCode`/`locale`/`version`.
- Chèn dữ liệu dynamic vào subject và body.
- Escape HTML text node và attribute đúng ngữ cảnh.
- Tạo bản plain text và HTML khi cần.
- Xử lý locale-specific date, number và currency format.
- Ngăn template truy cập dữ liệu không được cung cấp.
- Báo lỗi rõ khi thiếu resource hoặc biến bắt buộc.

Renderer không có lý do để gọi SMTP. Nó chỉ tạo nội dung.

## 10. Unit test renderer khác unit test selector

Một test renderer có thể dùng template resource thật và dữ liệu cố định:

~~~java
@Test
void rendersOrderCodeIntoBothBodies() {
    TemplateSelection selection = new TemplateSelection(
            "mail/order-confirmed",
            Locale.forLanguageTag("vi-VN"),
            1
    );

    OrderMailViewModel model =
            new OrderMailViewModel(
                    "buyer@example.org",
                    "Minh",
                    "ORD-2048"
            );

    RenderedMail rendered =
            renderer.render(selection, model);

    assertTrue(
            rendered.subject().contains("ORD-2048")
    );

    assertTrue(
            rendered.plainText().contains("ORD-2048")
    );

    assertTrue(
            rendered.htmlText().contains("ORD-2048")
    );
}
~~~

Ở đây `renderer` là instance của implementation cần kiểm thử với template fixture, không phải mock khiến test chỉ chứng minh mock trả về thứ đã cấu hình.

Một test khác bảo vệ escaping:

~~~java
@Test
void escapesUntrustedCustomerNameInHtml() {
    TemplateSelection selection = new TemplateSelection(
            "mail/order-confirmed",
            Locale.forLanguageTag("vi-VN"),
            1
    );

    OrderMailViewModel model =
            new OrderMailViewModel(
                    "buyer@example.org",
                    "<img src=x onerror=alert(1)>",
                    "ORD-2048"
            );

    RenderedMail rendered =
            renderer.render(selection, model);

    assertFalse(
            rendered.htmlText().contains(
                    "<img src=x onerror=alert(1)>"
            )
    );
}
~~~

Ví dụ này chỉ kiểm tra chuỗi HTML nguy hiểm không xuất hiện nguyên dạng; trong test thực tế còn cần kiểm tra kết quả escape đúng theo ngữ cảnh, chẳng hạn `&lt;` và `&gt;`, đồng thời ngăn đưa dữ liệu untrusted vào URL, JavaScript hoặc CSS mà không có encoding/validation riêng.

### Thymeleaf: th:text và th:utext

Nếu dùng Thymeleaf để render HTML email:

~~~html
<p th:text="${customerName}">Tên khách hàng</p>
~~~

`th:text` thường escape dữ liệu theo ngữ cảnh text. `th:utext` đưa nội dung không escape, chỉ phù hợp với HTML đã được tin cậy hoặc sanitized theo hợp đồng. `MimeMessageHelper.setText(html, true)` **không phải HTML sanitizer**.

Lỗi escape, ngày tháng hoặc resource thiếu thuộc **renderer tests**, không phải transport tests.

## 11. Transport chỉ nhận nội dung đã render

Tạo abstraction:

~~~java
public interface MailGateway {
    void send(RenderedMail mail);
}
~~~

Một implementation dùng Spring Mail:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringMailGateway implements MailGateway {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public SpringMailGateway(
            JavaMailSender mailSender,
            String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    @Override
    public void send(RenderedMail mail) {
        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message, true, "UTF-8"
                    );

            helper.setFrom(fromAddress);
            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(
                    mail.plainText(),
                    mail.htmlText()
            );

        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Không thể chuẩn bị MIME message", ex
            );
        }

        mailSender.send(message);
    }
}
~~~

`MailPreparationException` là exception runtime do ứng dụng định nghĩa. `JavaMailSender.send` có thể ném `MailException` như `MailSendException`. Nếu muốn đóng gói lỗi transport thành một exception/domain-independent error chung, làm ở gateway hoặc adapter theo quy ước, nhưng không để selector xử lý lỗi SMTP.

### Vì sao From được inject, không nằm trong selection?

`From` thường gắn với sender identity, account và policy vận hành. Template selection quyết định nội dung, không nhất thiết quyết định credential SMTP. Hệ thống nhiều account có thể có một `MailRoutingGateway` chọn transport theo `MailPurpose` đã được application service kiểm soát.

Không cho template file tự quyết định SMTP username/password.

## 12. Test transport bằng Mockito mà không gửi thư thật

Ở transport test, tạo `MimeMessage` trong bộ nhớ bằng Jakarta Mail rồi mock `JavaMailSender`. Mục tiêu là kiểm tra gateway **tạo message và gọi sender** đúng cách, không mở kết nối mạng.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.util.Properties;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class SpringMailGatewayTest {

    @Test
    void sendsRenderedContentAsMimeMessage()
            throws Exception {

        JavaMailSender sender =
                mock(JavaMailSender.class);

        when(sender.createMimeMessage())
                .thenAnswer(invocation ->
                        new MimeMessage(
                                Session.getInstance(
                                        new Properties()
                                )
                        )
                );

        SpringMailGateway gateway =
                new SpringMailGateway(
                        sender,
                        "orders@example.org"
                );

        RenderedMail mail = new RenderedMail(
                "buyer@example.org",
                "Xác nhận đơn hàng ORD-2048",
                "Đơn hàng ORD-2048 đã xác nhận.",
                "<p>Đơn hàng ORD-2048 đã xác nhận.</p>"
        );

        gateway.send(mail);

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender, times(1)).send(captor.capture());

        MimeMessage actual = captor.getValue();

        assertEquals(
                mail.subject(),
                actual.getSubject()
        );

        InternetAddress to = (InternetAddress)
                actual.getRecipients(
                        Message.RecipientType.TO
                )[0];

        assertEquals(
                "buyer@example.org",
                to.getAddress()
        );

        InternetAddress from =
                (InternetAddress) actual.getFrom()[0];

        assertEquals(
                "orders@example.org",
                from.getAddress()
        );

        assertTrue(actual.isMimeType("multipart/*"));
    }
}
~~~

Test này không cần instantiate `MailTemplateSelector`, không có `OrderRepository`, không khởi động SMTP server và không biết vì sao subject có nội dung ORD-2048. Nó chỉ xác nhận contract của **transport adapter**.

### Vì sao mock JavaMailSender nhưng dùng MimeMessage thật?

Nếu mock cả `MimeMessage` và `MimeMessageHelper` bằng các stub rời rạc, test rất dễ chỉ xác nhận chi tiết gọi method, không chứng minh header hoặc MIME content thực được dựng đúng.

Dùng một `MimeMessage` thật trong bộ nhớ có lợi:

- Các setter của `MimeMessageHelper` thực sự thay đổi MIME object.
- Có thể kiểm tra recipient/header/content type.
- Không gửi ra network.
- Không cần biết template đã được chọn bằng rule nào.

Đây là ranh giới hợp lý của một **unit test cho gateway**, vẫn dựa vào thư viện Jakarta Mail nội bộ.

## 13. Kiểm tra plain text và HTML trong transport test

Khi `MimeMessageHelper` nhận cả plain và HTML:

~~~java
helper.setText(
        "Đơn hàng ORD-2048 đã được xác nhận.",
        "<p>Đơn hàng <strong>ORD-2048</strong> đã được xác nhận.</p>"
);
~~~

Spring Mail tạo cấu trúc MIME thích hợp để client có thể chọn giữa plain text và HTML. Với `MimeMessageHelper(message, true, "UTF-8")`, structure có thể chứa `multipart/mixed` bao bên ngoài và một `multipart/alternative` bên trong.

Vì vậy, không nên giả định:

~~~java
MimeMultipart multipart =
        (MimeMultipart) message.getContent();

// Phần tử 0 luôn là plain text,
// phần tử 1 luôn là HTML.
~~~

Giả định này có thể sai nếu MIME structure thay đổi hoặc có attachment. Test tốt nên xem **các part theo MIME type**, không dựa cứng vào vị trí của chúng.

Có thể dùng một helper đệ quy trong test:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

private static String findPartText(
        Part part,
        String mimeType) throws Exception {

    if (part.isMimeType(mimeType)) {
        Object content = part.getContent();

        if (content instanceof String text) {
            return text;
        }
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();

        for (int i = 0; i < multipart.getCount(); i++) {
            String found = findPartText(
                    multipart.getBodyPart(i),
                    mimeType
            );

            if (found != null) {
                return found;
            }
        }
    }

    return null;
}
~~~

Sau đó:

~~~java
MimeMessage message = captor.getValue();

assertEquals(
        "Đơn hàng ORD-2048 đã được xác nhận.",
        findPartText(message, "text/plain")
);

assertTrue(
        findPartText(message, "text/html")
                .contains("<strong>ORD-2048</strong>")
);
~~~

Đây là helper kiểm thử cho trường hợp text/plain và text/html thông thường. Nếu MIME có embedded `message/rfc822` hoặc content đặc biệt, có thể cần extractor phù hợp hơn.

### Test Unicode

Nếu cần bảo vệ encoding tiếng Việt:

~~~java
assertEquals(
        "Thông báo thanh toán – Đơn hàng số 2048",
        actual.getSubject()
);
~~~

Có thể kiểm tra body Unicode và charset qua MIME part. Không nhất thiết kiểm tra chính xác chuỗi encoded-word raw trong header vì cách Jakarta Mail encode/fold header có thể khác nhau mà vẫn hợp lệ. Hãy kiểm tra giá trị **decoded** hoặc ý nghĩa MIME, không assert byte-for-byte theo một phiên bản thư viện.

## 14. Test lỗi transport, không làm selector chịu trách nhiệm

Nếu `JavaMailSender` ném lỗi:

~~~java
@Test
void propagatesDeliveryFailure() {
    JavaMailSender sender =
            mock(JavaMailSender.class);

    when(sender.createMimeMessage())
            .thenReturn(
                    new MimeMessage(
                            Session.getInstance(
                                    new Properties()
                            )
                    )
            );

    doThrow(new MailSendException("SMTP unavailable"))
            .when(sender)
            .send(any(MimeMessage.class));

    SpringMailGateway gateway =
            new SpringMailGateway(
                    sender,
                    "orders@example.org"
            );

    RenderedMail mail = new RenderedMail(
            "buyer@example.org",
            "Thông báo",
            "Plain text",
            "<p>HTML</p>"
    );

    assertThrows(
            MailSendException.class,
            () -> gateway.send(mail)
    );
}
~~~

Ví dụ trên giả định gateway **giữ nguyên** `MailException` do sender ném. Nếu ứng dụng chủ động chuyển exception thành một `MailDeliveryException` riêng, assertion nên dùng kiểu exception theo hợp đồng của gateway. Không bắt/nuốt mọi lỗi rồi coi như gửi thành công.

Các trường hợp khác:

- `mailSender.createMimeMessage()` thất bại bất thường.
- Recipient hoặc From không hợp lệ khiến chuẩn bị MIME báo lỗi.
- Provider từ chối AUTH/TLS.
- Lỗi kết nối tạm thời.
- Partial recipient acceptance.
- SMTP timeout và kết quả chưa chắc chắn.
- Attachment không đọc được hoặc vượt giới hạn.

Những lỗi này thuộc gateway/transport hoặc orchestration retry, không phải bảng ánh xạ locale → template.

### Đừng retry SMTP trong selector

Một phương thức `select(...)` không nên biết `MailSendException` và cũng không nên tự ngủ/backoff. Retry thuộc mail worker/delivery policy sau khi transport thất bại. Selector chỉ nên ném lỗi như `TemplateUnavailableException` khi không thể xác định template hợp lệ.

## 15. Unit test application handler: kiểm tra luồng điều phối

Một application handler có thể kết hợp selector, renderer và gateway:

~~~java
@Service
public class OrderConfirmationMailHandler {

    private final MailTemplateSelector selector;
    private final MailTemplateRenderer renderer;
    private final MailGateway gateway;

    public OrderConfirmationMailHandler(
            MailTemplateSelector selector,
            MailTemplateRenderer renderer,
            MailGateway gateway) {
        this.selector = selector;
        this.renderer = renderer;
        this.gateway = gateway;
    }

    public void send(OrderMailViewModel model, Locale locale) {
        TemplateSelection selection = selector.select(
                MailPurpose.ORDER_CONFIRMED,
                locale
        );

        RenderedMail mail =
                renderer.render(selection, model);

        gateway.send(mail);
    }
}
~~~

Ở production, handler còn cần authorization, recipient policy và dữ liệu domain tin cậy trước khi tạo view model. Ví dụ cố ý giản lược để thể hiện **quy trình chọn → render → gửi**.

Unit test handler tập trung xác nhận các dependency được dùng đúng:

~~~java
@Test
void coordinatesSelectionRenderingAndDelivery() {
    MailTemplateSelector selector =
            mock(MailTemplateSelector.class);
    MailTemplateRenderer renderer =
            mock(MailTemplateRenderer.class);
    MailGateway gateway =
            mock(MailGateway.class);

    TemplateSelection selection = new TemplateSelection(
            "mail/order-confirmed",
            Locale.forLanguageTag("vi-VN"),
            1
    );

    OrderMailViewModel model = new OrderMailViewModel(
            "buyer@example.org",
            "Minh",
            "ORD-2048"
    );

    RenderedMail rendered = new RenderedMail(
            model.recipient(),
            "Đã xác nhận ORD-2048",
            "Nội dung văn bản",
            "<p>Nội dung HTML</p>"
    );

    when(selector.select(
            MailPurpose.ORDER_CONFIRMED,
            Locale.forLanguageTag("vi-VN")
    )).thenReturn(selection);

    when(renderer.render(selection, model))
            .thenReturn(rendered);

    OrderConfirmationMailHandler handler =
            new OrderConfirmationMailHandler(
                    selector,
                    renderer,
                    gateway
            );

    handler.send(
            model,
            Locale.forLanguageTag("vi-VN")
    );

    verify(renderer).render(selection, model);
    verify(gateway).send(rendered);
}
~~~

Nếu `MailTemplateSelector` là `final` và dự án không cấu hình Mockito hỗ trợ mock final class, có thể phụ thuộc vào một interface `TemplateSelector` thay vì class cụ thể. Đây cũng là lợi ích kiến trúc: abstraction nên biểu đạt hợp đồng mà handler cần, không phải chi tiết implement.

### Kiểm tra trường hợp selector từ chối

~~~java
@Test
void doesNotSendWhenTemplateIsUnavailable() {
    when(selector.select(
            any(),
            any()
    )).thenThrow(
            new TemplateUnavailableException(
                    "Thiếu template"
            )
    );

    assertThrows(
            TemplateUnavailableException.class,
            () -> handler.send(
                    model,
                    Locale.forLanguageTag("vi-VN")
            )
    );

    verifyNoInteractions(renderer, gateway);
}
~~~

Test này chứng minh **fail-fast**: khi không có template, ứng dụng không gọi renderer hoặc SMTP. Nó không cần tạo một server SMTP giả để kiểm tra logic đó.

## 16. Tránh mock quá sâu

Một anti-pattern:

~~~java
when(templateEngine.process(anyString(), any()))
        .thenReturn("<p>Hello</p>");

when(mailSender.createMimeMessage())
        .thenReturn(mock(MimeMessage.class));

// Mock helper, Session, MimeMultipart, MailSender,
// controller, repository, locale resolver...
~~~

Test có rất nhiều stub nhưng thực tế chỉ xác nhận “khi A trả X thì B được gọi”. Nó có thể bỏ sót lỗi MIME/encoding thật vì toàn bộ object đã bị mock.

Phương pháp tách hợp lý:

- **Selector test:** dùng catalog thật trong bộ nhớ, không mock dependency nếu không cần.
- **Renderer test:** dùng template resource hoặc template engine thật nhưng không gửi mail.
- **Gateway test:** dùng `MimeMessage` thật và `JavaMailSender` giả.
- **Handler test:** mock selector/renderer/gateway để kiểm tra orchestration.
- **SMTP integration test:** dùng test SMTP server để kiểm tra giao thức khi cần.

Mock đúng ranh giới giúp test vừa nhanh vừa có ý nghĩa.

## 17. Fake MailGateway để kiểm thử workflow

Không phải mọi test đều cần Mockito. Một fake gateway có thể lưu email đã gửi vào bộ nhớ:

~~~java
public final class CapturingMailGateway
        implements MailGateway {

    private final List<RenderedMail> sent =
            new ArrayList<>();

    @Override
    public void send(RenderedMail mail) {
        sent.add(mail);
    }

    public List<RenderedMail> captured() {
        return List.copyOf(sent);
    }
}
~~~

Một application integration test (không SMTP) có thể dùng fake này để xác nhận:

- Có đúng một email logic được yêu cầu.
- Recipient đã được chọn đúng bởi recipient policy.
- Subject/body chứa dữ liệu đã render.
- Không có email khi nghiệp vụ từ chối.

Nếu test chạy nhiều thread/`@Async`, `ArrayList` trên không thread-safe; cần dùng collection đồng bộ hoặc thiết kế synchronization thích hợp và tránh assertion trước khi worker hoàn tất.

### Fake gateway không chứng minh MIME đúng

Fake `MailGateway` nhận `RenderedMail` mà không dựng MIME. Nó **không kiểm tra** encoding, header, boundary, transport exception hay SMTP session. Những việc đó thuộc gateway unit test và SMTP integration test.

Mỗi test double phải được sử dụng đúng ý nghĩa của nó.

## 18. Tách lựa chọn template với cấu hình sender

Trong ứng dụng có nhiều SMTP account:

~~~text
ORDER_CONFIRMED → transactionalMailSender
PASSWORD_RESET  → securityMailSender
NEWSLETTER      → marketingMailSender
~~~

Đây là **sender routing policy**, khác với template selection:

~~~text
ORDER_CONFIRMED + vi-VN
    → mail/order-confirmed (vi-VN)
~~~

Không trộn hai map thành một khối khó kiểm thử.

Có thể định nghĩa:

~~~java
public interface MailSenderRouter {
    MailGateway route(MailPurpose purpose);
}
~~~

Và:

~~~java
public interface TemplateSelector {
    TemplateSelection select(
            MailPurpose purpose,
            Locale locale);
}
~~~

Sau đó viết hai nhóm unit test:

- `TemplateSelectorTest`: purpose/locale/variant → descriptor.
- `MailSenderRouterTest`: purpose/tenant/environment → account/gateway được phép.

Một test routing có thể xác nhận `NEWSLETTER` không được dùng security sender ngay cả khi marketing account lỗi. Điều đó vẫn không phải test HTML rendering.

## 19. Fallback locale là chính sách, không phải phép đo SMTP

Khi locale `fr-CA` chưa có bản dịch, có thể fallback:

~~~text
fr-CA -> fr -> en-US
~~~

Hoặc chính sách sản phẩm chọn fallback về `vi-VN`. Test selector cần xác nhận chính xác thứ tự.

Không nên để renderer tự fallback không báo gì nếu selector đã trả một locale được cho là hợp lệ, vì:

- Test selector có thể pass nhưng renderer lại dùng ngôn ngữ khác.
- Log không thể xác định template đã render.
- Hệ thống có thể gửi email sai ngôn ngữ.
- Cần kiểm soát riêng các loại email nhạy cảm như security notification.

Một mô hình rõ ràng là `TemplateSelection` mang **resolved locale**. Renderer dùng đúng locale này và báo lỗi nếu resource không tồn tại, thay vì tự đoán một locale nữa.

### Locale dạng language vs language-region

`Locale.forLanguageTag("en-US")` và `Locale.forLanguageTag("en-GB")` không nhất thiết cùng cách định dạng ngày/tiền tệ. Cần quyết định catalog dùng exact tags, chỉ language, hoặc fallback nhiều cấp.

Test selector theo các rule đã định; test renderer mới kiểm tra định dạng date/number/currency.

## 20. Template version, biến thể và A/B test

Khi template thay đổi, có thể có:

~~~text
mail/order-confirmed / vi-VN / v1
mail/order-confirmed / vi-VN / v2
~~~

Selector quyết định version/variant theo feature flag, tenant, campaign hoặc chính sách rollout.

Ví dụ hợp đồng:

~~~java
public record TemplateContext(
        MailPurpose purpose,
        Locale locale,
        UUID tenantId,
        String campaignId) {
}
~~~

Cần tránh trộn một nguồn ngẫu nhiên khó kiểm soát trong selector test. Nếu chọn biến thể bằng phân bổ nhất quán:

~~~text
stableRecipientOrEventId -> variant A/B
~~~

hãy inject strategy/seed rõ ràng và test:

- Cùng id cho cùng variant khi retry.
- Hai tenant có rule khác nhau không nhầm template.
- Flag tắt thì dùng version ổn định.
- Template unavailable thì fail/fallback đúng policy.
- Không phát sinh content khác cho cùng một outbox job trừ khi được chủ đích.

### Retry không nên âm thầm đổi template

Một job được gửi lại sau timeout có thể dùng cùng rendered snapshot hoặc cùng template version. Nếu selector chọn lại version mới dựa vào trạng thái rollout hiện tại, cùng một ý định gửi có thể tạo nội dung khác nhau giữa các attempt.

Với outbox, nên lưu template selection/version hoặc rendered snapshot theo chính sách. Test **idempotency của selection** tách khỏi test SMTP retry.

## 21. Kiểm thử negative cases có giá trị cao

Một test chỉ kiểm tra “đã chọn đúng template” chưa đủ. Các trường hợp từ chối quan trọng:

| Lỗi | Lớp chịu trách nhiệm | Test mong đợi |
| --- | --- | --- |
| Purpose không tồn tại trong catalog | Selector | Ném lỗi selection |
| Locale chưa hỗ trợ và không có fallback | Selector | Fail theo rule |
| Template resource bị thiếu | Renderer | Lỗi rendering, không gọi gateway |
| Giá trị HTML chưa được escape | Renderer | Không chứa markup untrusted |
| Address không hợp lệ khi dựng MIME | Gateway/validation boundary | Lỗi phù hợp |
| SMTP host unreachable | Transport | Lỗi delivery/retryable |
| Username/password SMTP sai | Transport/provider integration | Auth failure được phân loại |
| Quota SMTP bị chặn | Transport/worker | Backoff, không thử lại nóng |
| Recipient không có quyền nhận | Application policy | Không gọi selector/gateway khi đã từ chối |
| Duplicate event/outbox | Application/outbox | Không tạo thêm ý định gửi |

Khi test thất bại, tên test và lớp cần chỉ ra ranh giới sai. Ví dụ `fallsBackToVietnameseWhenFrenchTemplateUnavailable` không được phụ thuộc vào SMTP sandbox.

## 22. Kiểm thử nội dung Unicode và MIME đúng lớp

Giả sử tên khách hàng chứa ký tự Việt:

~~~text
Nguyễn Thị Ánh
~~~

Và subject:

~~~text
Hóa đơn tháng 11 – Đơn hàng ORD-2048
~~~

Các câu hỏi cần tách:

- Template engine có render đúng tên/subject không? → **Renderer test**.
- `MimeMessageHelper` có tạo header Unicode hợp lệ và body UTF-8 không? → **Gateway test**.
- SMTP relay thực tế có chấp nhận message không? → **Integration/contract test**.

Không cần chạy ba bài kiểm thử giống hệt nhau qua provider thật. Có thể dùng một fixture Unicode điển hình tại từng ranh giới và assert đúng kết quả cấp đó.

### Đừng assert MIME boundary sinh ngẫu nhiên

Multipart boundary, header folding, Content-Transfer-Encoding hoặc Message-ID có thể khác theo thư viện/runtime. Với gateway test, assert MIME semantics:

- Có recipient/from/subject đúng.
- Có phần text/plain.
- Có phần text/html.
- Charset và nội dung Unicode được giải mã đúng.
- Attachment có filename và content type hợp lệ nếu use case có attachment.

Không so sánh toàn bộ MIME serialization byte-for-byte trừ khi bạn thực sự đang kiểm thử một định dạng wire-level được cố định; điều này thường làm test brittle.

## 23. Test attachment và inline images ở transport, không ở selector

Một số template cần logo inline hoặc hóa đơn PDF. Selector có thể chọn một descriptor “invoice-ready”, nhưng không nên biết đường dẫn file vật lý hoặc cách Jakarta Mail gắn attachment.

Transport gateway có thể cần gọi:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes)
);
~~~

Hoặc:

~~~java
helper.addInline(
        "brandLogo",
        logoResource,
        "image/png"
);
~~~

Test transport nên kiểm tra:

- Attachment có filename, MIME type và bytes phù hợp.
- Resource còn tồn tại trong vòng đời `send(...)`.
- Inline content ID khớp với HTML được render.
- Với HTML và inline resource, gọi `helper.setText(...)` trước khi thêm inline resource theo quy ước của `MimeMessageHelper` để tránh lỗi tham chiếu ở một số mail client.
- Error của resource stream được phân loại đúng.

Test selector chỉ xác nhận chọn template cần hoặc không cần attachment theo rule nếu đó là một phần của metadata selection; nó không cần parse PDF hoặc MIME.

## 24. Kiểm thử đúng trách nhiệm của Spring context

Một unit test selector có thể instantiate class bằng `new`. Nhưng muốn xác nhận `@Configuration` tạo đủ bean, template resolver tìm đúng resource và `@Qualifier` inject đúng `JavaMailSender`, cần integration test wiring với Spring context.

Ví dụ các nhóm test:

~~~text
MailTemplateSelectorTest
    pure Java, JUnit
MailTemplateRendererTest
    template engine + resource
SpringMailGatewayTest
    JavaMailSender mock + real MimeMessage
OrderConfirmationMailHandlerTest
    mocked collaborator boundaries
MailConfigurationTest
    Spring context + test properties
MailSmtpIntegrationTest
    test SMTP server / provider sandbox
~~~

**Không cần đặt `@SpringBootTest` trên tất cả**. Context khởi động chậm, dễ phụ thuộc environment variable và có thể vô tình kết nối provider nếu cấu hình test không được cách ly.

### Cấu hình mail test phải an toàn

- Không dùng username/password production.
- Dùng mock/fake `JavaMailSender` cho unit/component test.
- Với SMTP integration, dùng test server tại loopback/container hoặc provider sandbox chuyên dụng.
- Tắt gửi thật ở local/CI bằng cấu hình test an toàn.
- Test cần assert email gửi phải dùng recipient test, không dùng dữ liệu thật.

Tách cấp test giúp vừa nhanh vừa tránh side effect.

## 25. Khi nào cần SMTP integration test?

Unit test gateway bằng `MimeMessage` trong bộ nhớ chứng minh construction/call đúng, nhưng không đảm bảo:

- Host/port cấu hình chính xác.
- TLS handshake/hostname verification hoạt động.
- SMTP AUTH với provider hợp lệ.
- Server chấp nhận sender identity/From.
- Provider quota/reply code đúng.
- Message size được server chấp nhận.
- Kết nối mạng/proxy hoạt động ở môi trường deploy.

Khi yêu cầu những điều này, cần test tích hợp với SMTP test server hoặc provider sandbox. Có thể dùng một server test SMTP kiểm soát được (ví dụ MailHog, GreenMail hoặc công cụ tương đương) nếu dự án đã lựa chọn.

Nhưng **đừng đưa logic chọn template vào SMTP integration test**. Test transport có thể dùng `RenderedMail` cố định như một fixture:

~~~java
RenderedMail testMail = new RenderedMail(
        "test-recipient@example.org",
        "Kiểm thử SMTP",
        "Đây là bản plain text.",
        "<p>Đây là bản HTML.</p>"
);

gateway.send(testMail);
~~~

Integration test có thể kiểm tra server test nhận được message và một vài trường cơ bản; nó không cần tạo order, invoice hoặc security token.

## 26. Mô hình “contract tests” giữa selector, renderer và gateway

Không nhất thiết mọi layer dùng chung một implementation test. Điều quan trọng là **hợp đồng dữ liệu**.

Ví dụ:

- Selector trả `TemplateSelection` có `templateCode`, `locale`, `version`.
- Renderer nhận đúng descriptor và typed view model, trả `RenderedMail`.
- Gateway nhận `RenderedMail` đã có `recipient`, `subject`, `plainText` và `htmlText`.

Các contract test cần bảo đảm:

1. Mọi descriptor được selector công bố đều có resource phù hợp.
2. Renderer thực thi được các template được support.
3. Không có template chứa biến bắt buộc ngoài view model contract.
4. Gateway chỉ cần rendered data, không cần một enum template.
5. Resource/template thiếu được báo rõ và không gửi.
6. HTML và plain text có ngữ nghĩa phù hợp với cùng nội dung.
7. Version/locale trong outbox được resolve nhất quán.

Một bài test catalog/resource availability có thể chạy khi build:

~~~java
for (TemplateSelection selection : catalog.all()) {
    assertTrue(
            templateRepository.exists(selection),
            "Thiếu template: " + selection
    );
}
~~~

`catalog.all()` và `templateRepository.exists` là API minh họa phải được ứng dụng triển khai. Đây là **contract/component test**, khác test logic selector thuần và khác test SMTP transport.

## 27. Tổ chức test data để giảm phụ thuộc

Nên dùng fixture factory có tên nghiệp vụ rõ ràng:

~~~java
public final class MailTestFixtures {

    private MailTestFixtures() {
    }

    public static OrderMailViewModel
    confirmedOrderVietnamese() {

        return new OrderMailViewModel(
                "buyer@example.org",
                "Lan",
                "ORD-2048"
        );
    }

    public static RenderedMail renderedOrderMail() {
        return new RenderedMail(
                "buyer@example.org",
                "Đơn hàng ORD-2048 đã xác nhận",
                "Nội dung văn bản ORD-2048",
                "<p>Nội dung HTML ORD-2048</p>"
        );
    }
}
~~~

Sử dụng theo lớp:

- Selector test tự tạo input purpose/locale, không cần `RenderedMail`.
- Renderer test dùng `TemplateSelection` và `OrderMailViewModel`.
- Gateway test dùng `RenderedMail`.
- Handler test dùng cả ba object nhưng mock collaborator.

Đừng tạo một factory khổng lồ chứa database entity, HTTP request, MIME session và SMTP property chỉ để hỗ trợ một phép assert chọn template. Fixture của tầng nào nên chứa dữ liệu phù hợp tầng đó.

### Test output có cần snapshot không?

Snapshot HTML hữu ích khi muốn kiểm soát layout lớn, nhưng cần thận trọng:

- Dynamic timestamp và random ID làm snapshot không ổn định.
- Thay whitespace hoặc template engine có thể gây nhiều diff vô nghĩa.
- Snapshot pass chưa chứng minh escaping hoặc link authorization đúng.
- Test chọn template không cần HTML snapshot.

Có thể kết hợp assertion có ý nghĩa cho phần trọng yếu, snapshot cho layout có chủ đích và một số visual/email-client test riêng.

## 28. Tách test khi có event, outbox và async worker

Một hệ thống gửi bất đồng bộ thường có:

~~~text
Domain event -> Outbox -> Worker
                           |
                           v
                    Template selector
                           |
                           v
                      Renderer
                           |
                           v
                     Mail gateway
~~~

Nên có các test độc lập:

- **Outbox test:** cùng event tạo đúng một job logic, retry không tạo duplicate enqueue.
- **Worker orchestration test:** worker claim job, gọi selector/renderer/gateway và ghi status.
- **Selector test:** chọn đúng template theo purpose/locale/version.
- **Renderer test:** tạo nội dung đúng/escape đúng.
- **Gateway test:** dựng MIME và gọi sender.
- **Retry test:** transport error được phân loại, backoff, không làm mất job.

Không cần dựng toàn bộ SMTP workflow để test việc một outbox job được dedupe. Ngược lại, gateway test không cần biết worker có claim lease hay không.

### Idempotency không nằm trong selector

Template selection phải nhất quán khi retry cùng ý định gửi nếu business policy yêu cầu; nhưng logic duy trì `idempotencyKey`, lease, attempt count và trạng thái `SENT` thuộc outbox/worker. Đừng thêm state database vào selector chỉ để chống retry gửi trùng.

## 29. Những lỗi kiểm thử thường gặp

### 29.1. Unit test template selector phụ thuộc SMTP server

**Vấn đề:** test về locale/purpose có thể fail vì network hoặc credential.

**Khắc phục:** instantiate selector với catalog thuần; assert descriptor.

### 29.2. Test transport tự quyết định template bằng một tên file

**Vấn đề:** gateway bắt đầu kiêm nhiệm business decision và renderer.

**Khắc phục:** truyền `RenderedMail` hoàn chỉnh vào gateway.

### 29.3. Mock tất cả, kể cả dữ liệu cần kiểm chứng

**Vấn đề:** mock `MimeMessage` khiến không có MIME thực để assert.

**Khắc phục:** dùng Jakarta Mail `MimeMessage` thật, mock `JavaMailSender`.

### 29.4. Gọi SMTP thật trong unit test

**Vấn đề:** chậm, flaky, rủi ro gửi ngoài ý muốn, phụ thuộc secret.

**Khắc phục:** dùng fake sender hoặc test server riêng cho integration.

### 29.5. Selector tự fallback, renderer lại fallback

**Vấn đề:** không biết email cuối cùng dùng locale nào.

**Khắc phục:** selector trả resolved locale; renderer dùng đúng hoặc báo lỗi.

### 29.6. Test mọi locale bằng cách parse MIME

**Vấn đề:** nặng, trùng coverage, khó biết lỗi ở đâu.

**Khắc phục:** test mapping locale ở selector; test một vài nội dung locale ở renderer; test MIME/UTF-8 ở gateway.

### 29.7. Assert raw MIME byte-for-byte

**Vấn đề:** boundary và header folding có thể thay đổi hợp lệ.

**Khắc phục:** assert decoded subject, recipient, MIME part và content type.

### 29.8. Chỉ kiểm tra email được gửi, bỏ qua lỗi template

**Vấn đề:** khi template thiếu, gateway vẫn có thể nhận nội dung rỗng hoặc sai.

**Khắc phục:** test negative path và xác nhận `verifyNoInteractions(gateway)`.

### 29.9. Dùng template name do client truyền

**Vấn đề:** có thể bỏ qua mapping nghiệp vụ hoặc chọn mẫu trái phép.

**Khắc phục:** chọn purpose từ use case có quyền; selector dùng catalog nội bộ.

### 29.10. Gộp sender account routing vào template selector

**Vấn đề:** đổi credential/SMTP provider kéo theo test template.

**Khắc phục:** tách `MailSenderRouter` khỏi `TemplateSelector`.

### 29.11. Dùng @SpringBootTest cho toàn bộ unit test

**Vấn đề:** chậm, dễ gặp lỗi cấu hình môi trường không liên quan.

**Khắc phục:** JUnit thuần cho selector; Spring context chỉ cho wiring/integration.

### 29.12. Test HTML chỉ tìm một chuỗi nhưng bỏ qua escaping

**Vấn đề:** nội dung có thể hiển thị nhưng còn XSS/HTML injection trong mail client.

**Khắc phục:** test renderer với input không đáng tin cậy và escape đúng ngữ cảnh.

### 29.13. Tin rằng SMTP accepted là delivered

**Vấn đề:** test thấy `send` không ném exception rồi ghi “khách hàng nhận thư”.

**Khắc phục:** phân biệt submitted/accepted với delivered; provider feedback cần test riêng.

### 29.14. Test async bằng assertion ngay sau khi submit

**Vấn đề:** worker có thể chưa hoàn tất, gây flaky test.

**Khắc phục:** dùng future, latch hoặc test scheduler/worker trực tiếp với deterministic executor, không dựa vào `Thread.sleep` tùy tiện.

### 29.15. Dùng Mockito verify quá chi tiết nội bộ

**Vấn đề:** đổi một helper call làm test fail dù output contract không đổi.

**Khắc phục:** assert các kết quả meaningful trên `TemplateSelection`, `RenderedMail` và `MimeMessage`; verify số lần gọi chỉ khi số lần thực sự quan trọng.

## 30. Bảng phân công test case

| Câu hỏi cần trả lời | Test ở đâu? | Có cần SMTP không? |
| --- | --- | --- |
| Order confirmed dùng template nào? | TemplateSelectorTest | Không |
| Locale thiếu thì fallback ra sao? | TemplateSelectorTest | Không |
| Version v2 có được chọn đúng? | TemplateSelectorTest | Không |
| Subject chứa order code chưa? | TemplateRendererTest | Không |
| Tên HTML untrusted có escape không? | TemplateRendererTest | Không |
| Template resource có thực sự tồn tại? | Renderer/catalog contract test | Không |
| Application handler có truyền đúng model? | HandlerTest | Không |
| Sender có được gọi một lần không? | MailGatewayTest | Không |
| To/From/Subject có đúng không? | MailGatewayTest | Không |
| Plain text và HTML có trong MIME không? | MailGatewayTest | Không |
| Unicode subject có round-trip đúng không? | MailGatewayTest | Không |
| TLS/AUTH hoạt động với relay thật? | SMTP integration test | Có, sandbox/test |
| Retry/backoff khi SMTP 4xx? | Worker/delivery policy test | Không cần thật |
| Outbox không tạo duplicate? | Outbox repository/worker test | Không |
| Provider đã giao thư tới inbox chưa? | Delivery feedback/integration | Không xác minh chỉ từ SMTP submit |

Bảng này cho thấy **test selector và test transport bổ sung cho nhau nhưng không thay thế nhau**. Càng rõ ranh giới, càng ít test phải kéo toàn bộ Spring application vào một phép assert đơn giản.

## 31. Bài tập suy luận

**Câu 1.** Bạn cần xác nhận `PASSWORD_RESET + vi-VN` chọn mẫu `mail/password-reset`. Có cần mock `JavaMailSender` không?

Không. Tạo selector với catalog kiểm thử và assert `TemplateSelection`. SMTP không tham gia quyết định.

**Câu 2.** Bạn muốn biết subject Unicode có được encode/decoded đúng trong MIME. Nên test ở selector hay gateway?

Ở gateway. Dùng `MimeMessage` thật trong bộ nhớ và kiểm tra `getSubject()` trả chuỗi Unicode đúng.

**Câu 3.** HTML có chứa raw `<img onerror=...>` từ tên khách hàng. Đây là lỗi của component nào?

Lỗi thuộc rendering/escaping boundary, không phải selector hay SMTP transport. Test renderer cần phát hiện.

**Câu 4.** Mock `MailGateway` rồi verify `send` được gọi có chứng minh MIME multipart đúng không?

Không. Fake/mock gateway không dựng MIME; cần test `SpringMailGateway` với `MimeMessage` thật.

**Câu 5.** Một test chọn locale fail vì SMTP credentials sai. Thiết kế test có vấn đề gì?

Nó gắn logic chọn template với hạ tầng transport. Nên tách unit test selector khỏi SMTP integration.

**Câu 6.** Locale `ja-JP` không có template, policy fallback về `vi-VN`. Assertion nên đặt ở đâu?

Trong selector test, trên `TemplateSelection.locale()` và template descriptor được chọn.

**Câu 7.** Worker retry một outbox job nhưng A/B selector chọn biến thể khác ở lần thứ hai. Có nguy cơ gì?

Cùng một ý định gửi có thể phát nội dung khác nhau. Nên dùng stable variant selection hoặc lưu version/snapshot và test tính nhất quán khi retry.

**Câu 8.** `JavaMailSender.send` ném `MailSendException`. Selector có nên bắt và retry không?

Không. Error handling, retry và backoff thuộc gateway/worker/delivery policy.

**Câu 9.** Có cần chạy `@SpringBootTest` cho test thuần mapping enum purpose sang template code?

Không. JUnit 5 với class Java thuần đã đủ nếu selector không phụ thuộc Spring context.

**Câu 10.** Test gateway assert toàn bộ MIME raw bytes bằng một snapshot cố định. Tại sao dễ lỗi giả?

Jakarta Mail có thể thay boundary, fold header hoặc encode hợp lệ khác theo phiên bản. Nên assert semantic decoded content.

**Câu 11.** Client gửi tên template qua HTTP body. Có nên tin để dựng email?

Không nên. Application service nên xác định business purpose và selector chọn template từ catalog tin cậy.

**Câu 12.** Test SMTP bằng sandbox pass có chứng minh mọi locale được chọn đúng không?

Không. Nó chỉ kiểm tra một phần tích hợp transport. Logic chọn template cần unit test và catalog/resource contract test riêng.

## 32. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Business command"] --> B["Recipient + authorization policy"]
    B --> C["TemplateSelector"]
    C --> D["TemplateSelection: code, locale, version"]
    D --> E["TemplateRenderer"]
    E --> F["RenderedMail: To, subject, plain, HTML"]
    F --> G["MailGateway"]
    G --> H["MimeMessageHelper"]
    H --> I["JavaMailSender"]
    I --> J["SMTP relay"]

    T1["Selector unit tests"] -. "Chọn template đúng" .-> C
    T2["Renderer tests"] -. "Nội dung / escape / locale" .-> E
    T3["Gateway unit tests"] -. "MIME / header / exception" .-> G
    T4["SMTP integration tests"] -. "AUTH / TLS / provider" .-> J
~~~

Các nguyên tắc quan trọng:

1. **Template selector quyết định mẫu**, dựa trên purpose, locale, version/variant và chính sách nghiệp vụ.
2. **Renderer biến template và view model thành nội dung**: subject, plain text, HTML, encoding theo ngữ cảnh.
3. **Transport nhận nội dung đã render và gửi**: To/From/Subject/MIME/attachment/`JavaMailSender`.
4. **Unit test selector không cần SMTP, Spring context hoặc Mockito** nếu mapping là logic thuần.
5. **Test renderer không cần gửi mail** nhưng cần kiểm tra resource, biến dữ liệu và escaping.
6. **Test gateway dùng `MimeMessage` thật, `JavaMailSender` giả**, assert các field và MIME semantics.
7. **Lỗi chọn template khác lỗi render và khác lỗi SMTP**; phân tầng exception và retry phù hợp.
8. **Không để client chọn template hoặc sender account tùy ý**; application layer kiểm soát business purpose.
9. **Không assert các chi tiết MIME không ổn định** như boundary ngẫu nhiên khi chỉ cần kiểm tra decoded subject/content.
10. **Dùng integration test có chủ đích** để xác minh Spring wiring và SMTP provider, không biến mọi unit test thành end-to-end test.
11. **Với outbox/async, giữ các test riêng** cho idempotency, worker orchestration, selection, rendering và transport.
12. **SMTP accepted chưa phải delivered**; feedback delivery và deliverability là phạm vi kiểm thử khác.

Tách kiểm thử logic chọn template khỏi kiểm thử transport khiến bài test phản ánh đúng kiến trúc: **selector trả lời “dùng mẫu nào”, renderer trả lời “nội dung gì”, còn gateway trả lời “đóng gói và gửi thế nào”**. Với Spring Framework Mail, ranh giới này giúp thay đổi ngôn ngữ, thiết kế template, nhà cung cấp SMTP hoặc cấu hình MIME mà không kéo theo một chuỗi test không liên quan, đồng thời làm rõ vị trí cần sửa khi lỗi thật sự xảy ra.
