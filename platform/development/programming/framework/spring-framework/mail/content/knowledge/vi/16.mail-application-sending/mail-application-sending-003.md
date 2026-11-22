# Dùng command hoặc DTO cho dữ liệu email

Khi một ứng dụng Spring cần gửi email xác nhận đơn hàng, nhắc lịch hoặc thông báo thanh toán, service gửi thư phải nhận được những dữ liệu cần thiết: người nhận, mã giao dịch, trạng thái, nội dung và có thể cả tệp đính kèm. Nếu truyền từng tham số rời rạc qua nhiều lớp, chữ ký phương thức sẽ dài, khó mở rộng và dễ nhầm thứ tự. Nếu truyền nguyên một entity hoặc một request object lớn, service email lại phụ thuộc vào nhiều dữ liệu không cần thiết.

Một cách tổ chức rõ ràng là dùng **command hoặc DTO (Data Transfer Object)** để đóng gói dữ liệu theo mục đích của từng ranh giới trong ứng dụng. Command biểu diễn **ý định yêu cầu thực hiện một hành động**, còn DTO biểu diễn **dữ liệu được chuyển giữa các lớp hoặc thành phần**. Hai khái niệm có thể dùng cùng kiểu Java, nhưng khác nhau về ý nghĩa và trách nhiệm.

Trong ngữ cảnh **Spring Framework Mail**, command thường mô tả yêu cầu nghiệp vụ như `SendOrderConfirmationCommand` hoặc `SendPasswordResetCommand`. DTO có thể chứa dữ liệu trình bày cho template như tên người nhận, mã đơn, ngày đến hạn và URL. Một service ứng dụng xử lý command, lấy dữ liệu có thẩm quyền, tạo model cho email, render nội dung rồi giao cho `JavaMailSender` gửi qua SMTP.

Bài này giải thích cách phân biệt command và DTO, chọn dữ liệu nên truyền, thiết kế record/class bất biến, kiểm tra đầu vào, tổ chức các lớp gửi email và những lỗi thường gặp khi đưa command/DTO vào Spring Mail.

## 1. Vì sao không truyền nhiều tham số rời rạc?

Một phương thức gửi thông báo ban đầu có thể rất đơn giản:

~~~java
public void sendOrderConfirmation(
        String recipient,
        String customerName,
        String orderCode,
        String status,
        BigDecimal total,
        LocalDate deliveryDate) {
    // Dựng và gửi email.
}
~~~

Khi email có thêm locale, URL, địa chỉ hỗ trợ và ghi chú, chữ ký tiếp tục dài:

~~~java
public void sendOrderConfirmation(
        String recipient,
        String customerName,
        String orderCode,
        String status,
        BigDecimal total,
        LocalDate deliveryDate,
        Locale locale,
        String detailsUrl,
        String supportEmail,
        String note) {
    // ...
}
~~~

Những vấn đề thường xuất hiện:

- Người gọi phải nhớ thứ tự của nhiều tham số cùng kiểu `String`.
- Khi thêm trường mới, phải sửa chữ ký và mọi nơi gọi.
- Không dễ biết trường nào bắt buộc, trường nào tùy chọn.
- Một số dữ liệu có thể thuộc các trách nhiệm khác nhau: dữ liệu request, dữ liệu nghiệp vụ, dữ liệu trình bày và thông tin SMTP.
- Unit test phải truyền nhiều đối số dù chỉ quan tâm một phần.

Có thể nhóm các giá trị liên quan thành một object:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderCode,
        String status,
        BigDecimal total,
        LocalDate deliveryDate) {
}
~~~

Service nhận một tham số có tên và cấu trúc rõ ràng:

~~~java
public void sendOrderConfirmation(OrderMailData data) {
    // Dùng dữ liệu đã đóng gói.
}
~~~

Object này giúp giảm số tham số, nhưng thiết kế tốt còn cần trả lời: **đây là command, request DTO hay view DTO?** Việc đặt tên và giới hạn trách nhiệm giúp người đọc hiểu được ai tạo dữ liệu, ai có quyền thay đổi nó và dữ liệu được dùng ở bước nào.

## 2. Command và DTO khác nhau thế nào?

**Command** biểu diễn một yêu cầu thực hiện hành động. Tên thường bắt đầu bằng động từ hoặc mô tả một ý định cụ thể, ví dụ:

- `SendOrderConfirmationCommand` — yêu cầu gửi email xác nhận đơn.
- `SendPasswordResetCommand` — yêu cầu gửi email đặt lại mật khẩu.
- `SendInvoiceCommand` — yêu cầu gửi hóa đơn.
- `NotifyPaymentFailedCommand` — yêu cầu thông báo thanh toán thất bại.

**DTO** là object mang dữ liệu qua một ranh giới. Nó không nhất thiết yêu cầu một hành động. Ví dụ:

- `OrderConfirmationRequest` — dữ liệu HTTP request gửi từ client.
- `OrderMailView` — dữ liệu cần để render template.
- `RenderedEmail` — subject và các representation body đã được tạo.
- `AttachmentDescriptor` — metadata tham chiếu tới tệp được phép đính kèm.

| Khía cạnh | Command | DTO |
| --- | --- | --- |
| Ý nghĩa | Yêu cầu thực hiện một hành động | Mang dữ liệu qua ranh giới |
| Câu hỏi trả lời | “Ứng dụng cần làm gì?” | “Thành phần này cần những dữ liệu nào?” |
| Tên thường gặp | `SendOrderConfirmationCommand` | `OrderMailView` |
| Có thể chứa dữ liệu? | Có, dữ liệu cần để thực hiện hành động | Có, đó là mục đích chính |
| Có tự thực hiện hành động? | Không; handler/service xử lý command | Không |
| Có nên chứa logic gửi SMTP? | Không | Không |
| Ví dụ sử dụng | Đầu vào của application service | Đầu vào của renderer/template |

Một command có thể được cài đặt bằng Java record và cũng là một DTO theo nghĩa rộng của object truyền dữ liệu. Sự khác nhau nằm ở **vai trò trong thiết kế**, không phải ở từ khóa Java hay việc object có method hay không.

Không nên biến sự khác biệt này thành quy tắc cứng rằng mọi object phải có hai loại class riêng. Với use case nhỏ, một record có tên command có thể đủ. Với hệ thống nhiều lớp, việc tách command khỏi view DTO thường giúp giữ ranh giới rõ ràng.

## 3. Luồng dữ liệu email trong ứng dụng Spring

Một luồng có thể chia thành các bước:

~~~mermaid
flowchart TD
    A["HTTP / Scheduler / Event"] --> B["Request DTO hoặc Event DTO"]
    B --> C["Application Service"]
    C --> D["Command / Use case"]
    D --> E["Đọc và kiểm tra dữ liệu nghiệp vụ"]
    E --> F["Mail View DTO"]
    F --> G["Template Renderer"]
    G --> H["RenderedEmail"]
    H --> I["Spring Mail Gateway"]
    I --> J["JavaMailSender"]
    J --> K["SMTP relay"]
~~~

Mỗi thành phần có trách nhiệm riêng:

1. **Request DTO hoặc event** mang dữ liệu từ bên ngoài vào.
2. **Application service/command handler** điều phối use case và áp dụng quy tắc nghiệp vụ.
3. **Mail view DTO** chỉ chứa dữ liệu cần hiển thị.
4. **Renderer** tạo subject, plain text và HTML.
5. **Mail gateway** chuyển nội dung đã chuẩn bị thành `MimeMessage` và gọi `JavaMailSender`.
6. **SMTP relay** tiếp nhận message theo cấu hình kết nối.

Không phải ứng dụng nào cũng cần đủ sáu class. Với một service nhỏ, có thể gộp renderer và gateway. Tuy nhiên, cần hiểu ranh giới để khi hệ thống lớn lên, phần nghiệp vụ không bị phụ thuộc trực tiếp vào chi tiết MIME hoặc SMTP.

## 4. Chọn command theo hành động nghiệp vụ

Một command tốt thể hiện **mục đích**, không chỉ liệt kê các trường email chung chung.

Ví dụ:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {
}
~~~

Command này nói rằng ứng dụng cần gửi xác nhận cho một đơn hàng. Nó không bắt buộc người gọi phải tự cung cấp toàn bộ tổng tiền, trạng thái, tên khách hàng và URL.

Application service có thể dùng `orderId` để tải dữ liệu có thẩm quyền từ repository, xác minh người nhận được phép nhận thông báo và dựng view model. Cách này tránh tin vào các giá trị quan trọng do client tự gửi.

Một command khác:

~~~java
public record SendPasswordResetCommand(
        UUID userId,
        String resetRequestId) {
}
~~~

Command chỉ định danh yêu cầu đặt lại mật khẩu. Service có thể kiểm tra trạng thái token, thời hạn và người nhận từ hệ thống xác thực. Không nên yêu cầu client truyền một địa chỉ email tùy ý rồi gửi token của một tài khoản tới địa chỉ đó.

### Command nên biểu diễn một use case

Một command như:

~~~java
public record SendEmailCommand(
        String recipient,
        String subject,
        String html,
        String plainText) {
}
~~~

có thể hữu ích ở một **hạ tầng gửi mail tổng quát**. Nhưng nếu dùng nó làm API công khai cho mọi nghiệp vụ, caller phải tự quyết định nội dung, người nhận, template và có thể cả những dữ liệu nhạy cảm. Khi đó, application service không còn kiểm soát được ý nghĩa của từng loại email.

Với nghiệp vụ quan trọng, command cụ thể thường rõ ràng hơn: `SendInvoiceCommand`, `SendWelcomeEmailCommand`, `SendAppointmentReminderCommand`. Một gateway tổng quát có thể nhận `RenderedEmail` ở tầng thấp hơn sau khi nghiệp vụ đã quyết định nội dung.

## 5. Request DTO, command và mail view DTO

Ba object có thể xuất hiện trong một luồng:

| Object | Ai tạo? | Chứa gì? | Ai sử dụng? |
| --- | --- | --- | --- |
| Request DTO | Controller/adapter nhận request | Dữ liệu client được phép gửi | Controller và application service |
| Command | Adapter hoặc application layer | Ý định nghiệp vụ và dữ liệu cần cho use case | Command handler/application service |
| Mail view DTO | Application service/mapper | Dữ liệu đã xác thực, định dạng cho email | Template renderer |

Ví dụ request DTO:

~~~java
public record OrderConfirmationRequest(
        @NotBlank
        @Email
        String recipient,
        @Size(max = 120)
        String messageToSeller) {
}
~~~

Request không nên cho client quyết định trạng thái đơn, số tiền hoặc template nội bộ. Những dữ liệu này cần được đọc từ domain/repository.

Command:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient,
        String messageToSeller) {
}
~~~

Mail view DTO:

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        String formattedTotal,
        String formattedDeliveryDate,
        String detailsUrl,
        String messageToSeller) {
}
~~~

Application service chuyển từ request sang command, rồi tải dữ liệu nghiệp vụ và tạo view DTO. Trong hệ thống không có HTTP controller, command có thể được tạo trực tiếp từ scheduler, message consumer hoặc một use case khác.

### Có bắt buộc phải có cả ba không?

Không. Nếu ứng dụng chỉ có một lớp gọi nội bộ, có thể dùng command làm đầu vào trực tiếp và không cần request DTO riêng. Nếu renderer chỉ cần hai giá trị đơn giản, view DTO có thể không cần class độc lập. Tách object khi nó **làm rõ một ranh giới hoặc hợp đồng**, không phải chỉ để tăng số lượng file.

## 6. Thiết kế command bất biến bằng Java record

Command thường là một snapshot dữ liệu tại thời điểm yêu cầu. Java record là lựa chọn phù hợp khi các trường có thể được biểu diễn bằng component bất biến:

~~~java
import java.util.UUID;

public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {
}
~~~

Record tự cung cấp constructor, accessor, `equals`, `hashCode` và `toString`. Các component được khai báo là final; object không có setter tự sinh.

Nếu command có collection, cần nhớ rằng record chỉ làm component reference bất biến, **không tự làm collection bên trong bất biến**. Hãy copy defensive:

~~~java
public record SendBulkNoticeCommand(
        List<String> recipients,
        String noticeCode) {

    public SendBulkNoticeCommand {
        recipients = List.copyOf(recipients);
        if (recipients.isEmpty()) {
            throw new IllegalArgumentException(
                    "Danh sách người nhận không được rỗng"
            );
        }
    }
}
~~~

`List.copyOf` tạo danh sách không thể thay đổi qua reference được giữ trong record và từ chối phần tử null. Với collection lồng nhau hoặc object mutable, cần xem xét sâu hơn.

### Khi nào dùng class thay vì record?

Dùng class khi cần:

- Tương thích với framework hoặc serializer yêu cầu constructor/setter cụ thể.
- Kế thừa hoặc cấu trúc object phức tạp mà record không phù hợp.
- Quản lý trạng thái mutable có chủ đích.
- Hành vi xây dựng object nhiều bước.

Không nên dùng mutable command chỉ vì muốn controller gán từng trường bằng setter. Nếu command đại diện yêu cầu đã được tạo, việc sửa dữ liệu giữa các bước có thể khiến log, retry và kết quả xử lý không còn cùng một snapshot.

## 7. Validation command và DTO

Validation có thể xảy ra ở nhiều ranh giới, nhưng mỗi loại kiểm tra trả lời câu hỏi khác nhau.

**Validation cấu trúc** kiểm tra dữ liệu có đủ và đúng định dạng cơ bản không:

- Recipient có rỗng không?
- Mã đơn có đúng định dạng không?
- Ghi chú có vượt giới hạn không?
- Danh sách người nhận có rỗng hoặc quá lớn không?

**Validation nghiệp vụ** kiểm tra yêu cầu có hợp lệ trong trạng thái hiện tại không:

- Đơn hàng đã tồn tại chưa?
- Đơn có được phép gửi xác nhận không?
- Người nhận có liên quan tới đơn không?
- Hóa đơn đã phát hành chưa?
- Yêu cầu reset password còn hiệu lực không?

**Authorization** kiểm tra actor có quyền yêu cầu hành động hay không. Một email address đúng cú pháp không chứng minh người gọi được quyền gửi dữ liệu cho địa chỉ đó.

Ví dụ command có validation đơn giản:

~~~java
public record SendOrderConfirmationCommand(
        @NotNull UUID orderId,
        @NotBlank @Email String recipient) {
}
~~~

Nếu dùng Bean Validation trong application service, có thể kích hoạt validation bằng cơ chế phù hợp với kiến trúc Spring, hoặc gọi validator tường minh. Không nên giả định mọi record tự động được validate chỉ vì có annotation.

Một constructor cũng có thể bảo vệ invariant cơ bản:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {

    public SendOrderConfirmationCommand {
        Objects.requireNonNull(orderId, "orderId");

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "recipient không được để trống"
            );
        }
    }
}
~~~

Kiểm tra cú pháp email đầy đủ nên dùng validator/thư viện phù hợp; không tự viết một regex phức tạp rồi coi đó là bằng chứng mailbox tồn tại.

## 8. Không tin dữ liệu client cho các giá trị nghiệp vụ quan trọng

Một request có thể chứa:

~~~json
{
  "orderId": "8b3d...",
  "recipient": "buyer@example.net",
  "orderStatus": "PAID",
  "totalAmount": 1000,
  "templateName": "admin-mail"
}
~~~

Nếu client được quyền gửi những trường này, ứng dụng phải xác định trường nào thật sự được phép. `orderStatus` và `totalAmount` thường phải lấy từ dữ liệu nghiệp vụ có thẩm quyền. `templateName` nên được ánh xạ từ một loại thông báo đã được cho phép, không dùng đường dẫn tùy ý.

Một command có thể chỉ cần:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {
}
~~~

Sau đó service đọc trạng thái và số tiền từ repository/domain. Điều này giúp tránh việc client tự sửa nội dung email để hiển thị một giao dịch chưa thanh toán như đã thanh toán.

### Recipient cũng cần kiểm tra quyền

Không phải lúc nào cũng đúng khi nhận recipient do client gửi. Với thông báo tài khoản, recipient có thể phải là email đã xác minh của user. Với hóa đơn, recipient có thể là địa chỉ liên hệ được đăng ký cho khách hàng. Nếu nghiệp vụ cho phép nhập email thay thế, phải kiểm tra quyền và ghi nhận lý do theo chính sách sản phẩm.

## 9. Tạo mail view DTO từ domain data

Một entity thường có nhiều trường và quan hệ không cần thiết cho email:

~~~java
class Order {
    // id, customer, payment, lineItems, internalNotes,
    // audit fields, persistence relations...
}
~~~

Không nên truyền nguyên entity vào template chỉ vì cần vài giá trị. Thay vào đó, tạo DTO trình bày:

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        String formattedTotal,
        String formattedDeliveryDate,
        String detailsUrl) {
}
~~~

Mapper hoặc application service tạo view:

~~~java
private OrderMailView toMailView(
        Order order,
        Customer customer,
        URI publicBaseUri,
        Locale locale) {

    return new OrderMailView(
            customer.getDisplayName(),
            order.getCode(),
            statusLabelFor(order.getStatus(), locale),
            moneyFormatter.format(order.getTotal(), locale),
            dateFormatter.format(order.getDeliveryDate(), locale),
            buildOrderUrl(publicBaseUri, order.getCode())
    );
}
~~~

Lợi ích:

- Template chỉ nhìn thấy dữ liệu cần trình bày.
- Không vô tình render internal notes hoặc dữ liệu nhạy cảm.
- Không kích hoạt lazy loading bất ngờ trong lúc render.
- Cách định dạng ngày/tiền được kiểm soát ở một nơi.
- Unit test renderer không cần khởi tạo JPA entity hoặc database.

View DTO không nên chứa `JavaMailSender`, `MimeMessage`, SMTP password hoặc service. Nó là **dữ liệu hiển thị**, không phải hạ tầng gửi thư.

## 10. Render subject, plain text và HTML từ cùng view DTO

Một email có thể có ba trường nội dung:

~~~java
public record RenderedEmail(
        String subject,
        String plainText,
        String html) {
}
~~~

Renderer nhận view DTO và tạo kết quả:

~~~java
public interface OrderMailRenderer {
    RenderedEmail render(OrderMailView view, Locale locale);
}
~~~

Triển khai có thể dùng Thymeleaf:

~~~java
@Component
public class ThymeleafOrderMailRenderer
        implements OrderMailRenderer {

    private final TemplateEngine templateEngine;

    public ThymeleafOrderMailRenderer(
            TemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    @Override
    public RenderedEmail render(
            OrderMailView view,
            Locale locale) {

        Context context = new Context(locale);
        context.setVariable("mail", view);

        String html = templateEngine.process(
                "mail/order-confirmed",
                context
        );

        String plain = """
                Xin chào %s,

                Đơn hàng %s: %s
                Tổng tiền: %s
                Giao dự kiến: %s

                Xem chi tiết:
                %s
                """.formatted(
                view.customerName(),
                view.orderCode(),
                view.statusLabel(),
                view.formattedTotal(),
                view.formattedDeliveryDate(),
                view.detailsUrl()
        );

        String subject =
                "Đơn hàng " + view.orderCode() + " đã được xác nhận";

        return new RenderedEmail(subject, plain, html);
    }
}
~~~

Template HTML cần dùng escaped output cho dữ liệu text, chẳng hạn `th:text` trong Thymeleaf. URL trong `th:href` phải được xây từ base URL đáng tin cậy và kiểm tra theo chính sách. Renderer không nên tự truy cập repository để tính lại trạng thái đơn.

### Tại sao cùng view DTO quan trọng?

Nếu plain text truy vấn lại đơn hàng sau khi HTML đã render, dữ liệu có thể thay đổi giữa hai lần đọc. Một representation có thể ghi “Đang xử lý”, representation kia ghi “Đã giao”. Dùng một snapshot/view DTO đảm bảo hai bản mô tả cùng một trạng thái.

## 11. Mail gateway chuyển RenderedEmail thành MimeMessage

Lớp gateway chịu trách nhiệm chi tiết Spring Mail:

~~~java
public interface MailGateway {
    void send(OutboundMail mail);
}
~~~

Một DTO ở ranh giới gửi:

~~~java
public record OutboundMail(
        String from,
        String recipient,
        String subject,
        String plainText,
        String html) {
}
~~~

Gateway triển khai bằng `JavaMailSender`:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class SpringMailGateway implements MailGateway {

    private final JavaMailSender mailSender;

    public SpringMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public void send(OutboundMail mail) {
        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom(mail.from());
            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(mail.plainText(), mail.html());

            mailSender.send(message);
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Không thể tạo MIME message", ex
            );
        } catch (MailException ex) {
            throw new MailDeliveryException(
                    "SMTP không chấp nhận thao tác gửi", ex
            );
        }
    }
}
~~~

`MailPreparationException` và `MailDeliveryException` trong ví dụ là exception riêng của ứng dụng cần định nghĩa. Có thể chọn cách xử lý khác tùy kiến trúc, nhưng nên phân biệt lỗi tạo message với lỗi gửi qua hạ tầng mail. Không bắt mọi exception rồi bỏ qua, vì khi đó application service không biết thao tác thất bại.

Một lưu ý kỹ thuật: `MimeMessageHelper` có thể ném `MessagingException` khi tạo hoặc sửa message; `JavaMailSender.send(...)` có thể ném `MailException`. Các exception cụ thể và cách phân loại lỗi cần dựa trên API/version đang dùng.

## 12. Ví dụ hoàn chỉnh: command → application service → DTO → gateway

### 12.1. Command

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {
}
~~~

### 12.2. Application service

~~~java
@Service
public class SendOrderConfirmationHandler {

    private final OrderRepository orderRepository;
    private final CustomerRepository customerRepository;
    private final OrderMailRenderer renderer;
    private final MailGateway mailGateway;
    private final URI publicBaseUri;

    public SendOrderConfirmationHandler(
            OrderRepository orderRepository,
            CustomerRepository customerRepository,
            OrderMailRenderer renderer,
            MailGateway mailGateway,
            @Value("¤{app.public-base-url}") URI publicBaseUri) {

        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
        this.renderer = renderer;
        this.mailGateway = mailGateway;
        this.publicBaseUri = publicBaseUri;
    }

    public void handle(SendOrderConfirmationCommand command) {
        Order order = orderRepository.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFoundException(
                        command.orderId()
                ));

        Customer customer = customerRepository
                .findById(order.getCustomerId())
                .orElseThrow(() -> new CustomerNotFoundException(
                        order.getCustomerId()
                ));

        validateRecipient(command.recipient(), customer);
        ensureConfirmationMayBeSent(order);

        Locale locale = customer.getPreferredLocale();

        OrderMailView view = toMailView(
                order,
                customer,
                publicBaseUri,
                locale
        );

        RenderedEmail rendered = renderer.render(view, locale);

        OutboundMail outbound = new OutboundMail(
                "orders@example.org",
                command.recipient(),
                rendered.subject(),
                rendered.plainText(),
                rendered.html()
        );

        mailGateway.send(outbound);
    }

    private void validateRecipient(
            String recipient,
            Customer customer) {
        // Kiểm tra cú pháp và quyền nhận theo nghiệp vụ.
    }

    private void ensureConfirmationMayBeSent(Order order) {
        // Kiểm tra trạng thái và quy tắc gửi.
    }

    private OrderMailView toMailView(
            Order order,
            Customer customer,
            URI baseUri,
            Locale locale) {
        // Map dữ liệu đã xác thực sang DTO trình bày.
        throw new UnsupportedOperationException("Implement mapping");
    }
}
~~~

Các repository, domain class và exception là thành phần của ứng dụng giả định. Phương thức `toMailView` được để ở dạng khung để thể hiện vị trí mapping; trong ứng dụng thật, triển khai bằng mapper/service cụ thể.

### 12.3. Gọi use case

Từ controller, scheduler hoặc một thành phần khác:

~~~java
handler.handle(
        new SendOrderConfirmationCommand(
                orderId,
                verifiedRecipient
        )
);
~~~

Caller chỉ yêu cầu một hành động cụ thể. Nó không phải tự biết cách tạo MIME, chọn charset, cấu trúc multipart hoặc gọi SMTP.

### Trách nhiệm nằm ở đâu?

| Thành phần | Trách nhiệm |
| --- | --- |
| `SendOrderConfirmationCommand` | Biểu diễn ý định gửi xác nhận đơn hàng |
| `SendOrderConfirmationHandler` | Điều phối use case và kiểm tra nghiệp vụ |
| `OrderMailView` | Mang dữ liệu cần cho template |
| `OrderMailRenderer` | Tạo subject/plain/HTML |
| `OutboundMail` | Mang message đã render tới gateway |
| `SpringMailGateway` | Tạo `MimeMessage` và gọi `JavaMailSender` |

Với một ứng dụng nhỏ, có thể gộp `OutboundMail` vào `RenderedEmail` hoặc để renderer trả thẳng một object phù hợp gateway. Việc tách riêng có ích khi renderer và gateway thuộc hai module hoặc cần kiểm soát người gửi/người nhận ở một tầng khác.

## 13. Dữ liệu attachment nên được biểu diễn thế nào?

Nếu email có file đính kèm, tránh đưa đường dẫn filesystem tùy ý từ request vào command:

~~~java
// Không nên cho client truyền đường dẫn file server.
public record SendInvoiceCommand(
        UUID invoiceId,
        String filePath) {
}
~~~

Đường dẫn có thể trỏ ra ngoài vùng lưu trữ được phép hoặc làm ứng dụng đọc file không liên quan. Thay vào đó, command có thể mang một định danh nghiệp vụ:

~~~java
public record SendInvoiceCommand(
        UUID invoiceId,
        String recipient) {
}
~~~

Application service lấy hóa đơn và file đã được kiểm tra từ storage. DTO nội bộ cho attachment có thể là:

~~~java
public record MailAttachment(
        String fileName,
        String contentType,
        Resource resource) {
}
~~~

Tuy nhiên, việc truyền `Resource` chỉ phù hợp ở tầng nội bộ nơi vòng đời và khả năng đọc của resource được kiểm soát. Không expose object này trực tiếp như JSON request DTO.

Với nhiều tệp, có thể copy danh sách:

~~~java
public record OutboundMail(
        String from,
        String recipient,
        String subject,
        String plainText,
        String html,
        List<MailAttachment> attachments) {

    public OutboundMail {
        attachments = List.copyOf(attachments);
    }
}
~~~

Trước khi đính kèm, ứng dụng cần kiểm tra quyền truy cập file, kích thước, loại nội dung thực tế, tên file hiển thị và chính sách malware scanning nếu phù hợp. DTO mô tả file không làm file tự an toàn.

## 14. Command cho gửi đồng bộ và gửi bất đồng bộ

Trong luồng đồng bộ, application service gọi gateway và chờ kết quả gửi:

~~~text
handle(command)
    -> load data
    -> render
    -> mailGateway.send(...)
    -> return
~~~

Cách này đơn giản, phù hợp khi yêu cầu gửi ít, latency chấp nhận được và caller cần biết ngay lỗi từ gateway.

Trong hệ thống lớn, có thể dùng command để tạo công việc gửi bất đồng bộ:

~~~java
public record QueueOrderConfirmationCommand(
        UUID orderId,
        String recipient,
        String requestId) {
}
~~~

Handler xác thực use case, lưu một mail job hoặc outbox record rồi trả kết quả tiếp nhận. Worker đọc job, dựng view model và gửi thư.

~~~mermaid
flowchart TD
    A["Application command"] --> B["Validate nghiệp vụ"]
    B --> C["Lưu outbox / mail job"]
    C --> D["Worker nhận job"]
    D --> E["Render email"]
    E --> F["JavaMailSender"]
    F --> G["Cập nhật trạng thái gửi"]
~~~

### Không nên đưa MimeMessage vào queue

`MimeMessage` là object hạ tầng có trạng thái và phụ thuộc Jakarta Mail. Nó không phải payload tốt cho hàng đợi bền vững. Nên lưu dữ liệu command/job có thể serialize, ví dụ loại thông báo, ID tài nguyên, recipient đã xác minh, locale và mã template được allowlist. Worker tạo message mới khi xử lý.

### Idempotency và retry

Nếu cùng một command được gửi hai lần do message queue redelivery hoặc caller retry, có thể gửi email trùng. Với thông báo quan trọng, cần có request ID hoặc idempotency key và trạng thái job được lưu bền vững.

Một record có thể gồm:

~~~text
request_id: order-confirmation:ORD-2048:v1
purpose: ORDER_CONFIRMATION
order_id: ORD-2048
recipient_id: customer-42
status: PENDING
attempt_count: 0
~~~

Đây là mô hình dữ liệu minh họa. Không nên lưu credential SMTP hoặc toàn bộ nội dung riêng tư trong payload log. Nếu job cần dùng dữ liệu thay đổi theo thời gian, hãy quyết định rõ lấy snapshot lúc tạo job hay lấy trạng thái mới nhất lúc worker xử lý.

## 15. Command và event không giống nhau

Một **command** yêu cầu ứng dụng thực hiện hành động: `SendInvoiceCommand`. Một **event** mô tả điều gì đã xảy ra: `InvoiceIssuedEvent`.

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Command | `SendInvoiceEmailCommand` | Hãy gửi email hóa đơn |
| Event | `InvoiceIssuedEvent` | Hóa đơn đã được phát hành |
| DTO | `InvoiceMailView` | Dữ liệu để trình bày hóa đơn trong email |

Có thể có event `InvoiceIssuedEvent` khiến một handler tạo command gửi mail. Hoặc handler event trực tiếp dựng và gửi email nếu kiến trúc đơn giản. Nhưng cần phân biệt ý nghĩa:

- Event thường là sự kiện đã xảy ra, không nên bị đổi tên thành một yêu cầu chưa thực hiện.
- Command có thể thất bại hoặc bị từ chối.
- DTO chỉ mang dữ liệu, không đại diện sự kiện hay hành động.

Khi gửi email theo event, cần xem xét event có thể được phát lại, xử lý nhiều lần hoặc đến trễ. Idempotency và chính sách gửi trùng vẫn quan trọng.

## 16. Command có nên chứa subject và HTML hoàn chỉnh?

Điều đó phụ thuộc vào tầng nhận command.

Với một **use case nghiệp vụ**, thường không nên yêu cầu caller tự cung cấp HTML:

~~~java
public record SendPaymentReminderCommand(
        UUID invoiceId,
        String recipient,
        String html) {
}
~~~

Nếu `html` được lấy từ request, caller có thể kiểm soát nội dung hiển thị, chèn markup không mong muốn hoặc tạo email không theo chuẩn thương hiệu. Hơn nữa, application service không còn bảo đảm nội dung phản ánh trạng thái hóa đơn.

Thay vào đó:

~~~java
public record SendPaymentReminderCommand(
        UUID invoiceId) {
}
~~~

Handler lấy recipient đã xác minh, dữ liệu hóa đơn và render template đã được ứng dụng quản lý.

Ở **hạ tầng gửi mail tổng quát**, một object `OutboundMail` có thể chứa subject và body đã render. Đây là ranh giới khác: nội dung đã được chuẩn bị và gateway chỉ chịu trách nhiệm gửi. Chỉ những thành phần được phép mới nên tạo object này.

### Khi nào nội dung do người dùng tùy biến được phép?

Nếu sản phẩm cho phép quản trị viên chỉnh nội dung email, cần một quy trình quản trị template: quyền chỉnh sửa, versioning, preview, kiểm tra placeholder, HTML sanitization và phê duyệt trước khi phát hành. Không biến một endpoint gửi mail thành công cụ gửi HTML tùy ý cho mọi người dùng.

## 17. Không để command phụ thuộc vào Spring Mail

Command thuộc tầng ứng dụng/nghiệp vụ nên tránh import các lớp hạ tầng như:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
~~~

Một command như sau làm lộ chi tiết gửi mail:

~~~java
public record SendEmailCommand(MimeMessage message) {
}
~~~

Nó khiến caller phải tạo MIME message trước khi yêu cầu use case, đảo ngược trách nhiệm và khó kiểm thử.

Thay vào đó, command chứa dữ liệu nghiệp vụ đơn giản:

~~~java
public record SendWelcomeEmailCommand(UUID userId) {
}
~~~

Application service điều phối, renderer tạo nội dung và gateway dùng Spring Mail. Nếu cần thay provider SMTP bằng API email khác, phần nghiệp vụ vẫn có thể giữ nguyên.

### Dependency inversion ở mức vừa đủ

Có thể định nghĩa một interface trong application module:

~~~java
public interface MailGateway {
    void send(OutboundMail mail);
}
~~~

Spring Mail adapter triển khai interface đó. Application service phụ thuộc abstraction; adapter phụ thuộc `JavaMailSender`. Không cần tạo nhiều interface cho từng phương thức nhỏ nếu dự án chỉ có một use case đơn giản. Mục tiêu là cô lập **chi tiết transport** khỏi logic nghiệp vụ.

## 18. Không truyền entity hoặc application context vào DTO

Một số cách làm có vẻ tiện nhưng tạo coupling:

~~~java
public record OrderMailData(
        Order order,
        ApplicationContext applicationContext) {
}
~~~

Template hoặc renderer khi đó có thể truy cập nhiều dữ liệu và service ngoài nhu cầu email. Điều này làm khó review, test và kiểm soát thông tin.

DTO nên là tập trường cụ thể:

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        String formattedTotal,
        String detailsUrl) {
}
~~~

Nếu template cần một danh sách item, tạo một DTO con chỉ chứa tên, số lượng và giá đã định dạng:

~~~java
public record OrderLineMailView(
        String productName,
        String quantityLabel,
        String formattedLineTotal) {
}
~~~

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        List<OrderLineMailView> items,
        String formattedTotal,
        String detailsUrl) {

    public OrderMailView {
        items = List.copyOf(items);
    }
}
~~~

Cách này giới hạn dữ liệu template được phép thấy và tránh vô tình truy cập lazy relationship hoặc field nội bộ.

## 19. Đặt tên command/DTO để đọc được ý định

Tên object nên cho thấy vai trò:

| Tên | Vai trò gợi ý |
| --- | --- |
| `SendWelcomeEmailCommand` | Yêu cầu gửi email chào mừng |
| `SendInvoiceCommand` | Yêu cầu gửi hóa đơn |
| `OrderConfirmationRequest` | Dữ liệu đầu vào từ API |
| `OrderMailView` | Dữ liệu trình bày cho email đơn hàng |
| `RenderedEmail` | Nội dung đã render |
| `OutboundMail` | Thông điệp chuẩn bị chuyển tới gateway |
| `MailAttachment` | Mô tả resource đính kèm nội bộ |

Tránh tên chung như `Data`, `MailInfo`, `EmailObject` nếu chúng không nói rõ object được dùng ở đâu. Nhưng cũng không cần tên quá dài chứa mọi chi tiết implementation.

Một dự án có thể quy định package:

~~~text
mail/
├── application/
│   ├── command/
│   │   └── SendOrderConfirmationCommand.java
│   └── SendOrderConfirmationHandler.java
├── model/
│   ├── OrderMailView.java
│   ├── RenderedEmail.java
│   └── OutboundMail.java
├── rendering/
│   └── ThymeleafOrderMailRenderer.java
└── infrastructure/
    └── SpringMailGateway.java
~~~

Cấu trúc trên chỉ là ví dụ. Có thể gom package theo feature `order` thay vì layer nếu dự án đang dùng feature-based organization. Điều quan trọng là command, view model và transport adapter có ranh giới dễ hiểu.

## 20. Test command handler và renderer

Command/DTO giúp unit test dễ hơn vì dữ liệu được đóng gói thành object rõ ràng.

### 20.1. Test handler điều phối đúng use case

Có thể mock repository, renderer và gateway:

~~~java
@Test
void sendsConfirmationForExistingOrder() {
    // Arrange:
    // - repository trả về order và customer
    // - renderer trả về RenderedEmail
    // - gateway là mock

    handler.handle(
            new SendOrderConfirmationCommand(
                    orderId,
                    "buyer@example.net"
            )
    );

    // Assert:
    // - renderer được gọi với OrderMailView đúng
    // - gateway được gọi với OutboundMail đúng
}
~~~

Test này kiểm tra **điều phối và dữ liệu truyền giữa các lớp**, không cần kết nối SMTP thật.

### 20.2. Test renderer với dữ liệu cố định

~~~java
OrderMailView view = new OrderMailView(
        "An <Bảo>",
        "ORD-2048",
        "Đã xác nhận",
        "1.250.000 ₫",
        "18/11/2026",
        "https://app.example.org/orders/ORD-2048"
);

RenderedEmail rendered = renderer.render(
        view,
        Locale.forLanguageTag("vi-VN")
);
~~~

Kiểm tra:

- Subject có mã đơn.
- Plain text có trạng thái, tổng tiền, ngày giao và URL.
- HTML có cùng dữ kiện.
- Tên có ký tự đặc biệt được escape trong HTML text.
- Plain text giữ tên ở dạng văn bản gốc.

### 20.3. Test gateway tách khỏi SMTP thật

Có thể dùng fake/mock `JavaMailSender` để kiểm tra gateway tạo `MimeMessage` với From, To, Subject và body phù hợp. Với kiểm thử giao thức, dùng SMTP test server hoặc sandbox riêng.

Không cần mọi unit test đều gửi email thật. Test SMTP thật có thể chậm, phụ thuộc mạng và vô tình gửi tới địa chỉ ngoài dự kiến nếu cấu hình test không tách biệt.

## 21. Các lỗi thường gặp khi dùng command hoặc DTO

### 21.1. Một DTO khổng lồ cho toàn bộ hệ thống

**Vấn đề:** object chứa recipient, SMTP host, password, template name, HTML, domain entity, file path và nhiều trường tùy chọn. Mỗi service chỉ dùng một phần.

**Cách xử lý:** tách theo ranh giới: command nghiệp vụ, view DTO, rendered content và transport DTO khi thật sự cần.

### 21.2. Dùng request DTO làm command ở mọi tầng

Request DTO phản ánh hợp đồng API bên ngoài. Nó có thể chứa trường client được phép gửi và annotation web validation. Application command nên biểu diễn use case của ứng dụng; hai object có thể trùng trường trong trường hợp nhỏ nhưng không bắt buộc phải là một.

### 21.3. Để client quyết định trạng thái hoặc số tiền email

**Vấn đề:** dữ liệu email có thể bị giả mạo nếu lấy từ request mà không xác minh.

**Cách xử lý:** tải dữ liệu từ repository/domain và kiểm tra quyền trước khi render.

### 21.4. Đưa MimeMessage vào command

**Vấn đề:** command phụ thuộc Jakarta Mail và buộc caller tạo message ở tầng sai.

**Cách xử lý:** command mang ý định nghiệp vụ; gateway tạo MIME message sau khi nội dung đã được render.

### 21.5. Đưa nguyên entity vào template

**Vấn đề:** lộ field không cần thiết, lazy loading và coupling với persistence.

**Cách xử lý:** tạo view DTO nhỏ và rõ kiểu.

### 21.6. Đưa HTML chưa kiểm soát vào command tổng quát

**Vấn đề:** mọi caller có thể tạo nội dung tùy ý, khó bảo đảm thương hiệu và chính sách bảo mật.

**Cách xử lý:** command nghiệp vụ chọn template được kiểm soát; chỉ tầng hạ tầng được phép nhận nội dung đã render.

### 21.7. DTO mutable bị thay đổi giữa lúc gửi

**Vấn đề:** một thành phần có thể sửa recipient hoặc nội dung sau khi command đã được tạo, làm retry và log không nhất quán.

**Cách xử lý:** ưu tiên record/immutable object và defensive copy cho collection.

### 21.8. Chỉ validate ở controller

**Vấn đề:** command cũng có thể được tạo từ scheduler, event consumer hoặc job nội bộ mà không qua controller.

**Cách xử lý:** đặt invariant và validation nghiệp vụ ở application/domain boundary; controller validation chỉ là lớp đầu vào bổ sung.

### 21.9. Dùng một command generic cho mọi loại email

**Vấn đề:** caller tự quyết định subject, HTML và template, khiến ý nghĩa nghiệp vụ biến mất.

**Cách xử lý:** command cụ thể cho use case; object generic chỉ ở mail infrastructure sau khi nội dung được chuẩn bị.

### 21.10. Không xử lý gửi trùng khi retry

**Vấn đề:** cùng command được thực thi nhiều lần có thể gửi nhiều email giống nhau.

**Cách xử lý:** dùng request ID/idempotency key, lưu trạng thái job và xác định chính sách retry.

### 21.11. Đưa đường dẫn file từ request vào attachment DTO

**Vấn đề:** ứng dụng có thể đọc file ngoài vùng cho phép.

**Cách xử lý:** dùng file ID/storage key được phân quyền, sau đó resolve thành Resource nội bộ đã kiểm tra.

### 21.12. Tách class chỉ vì muốn có nhiều class

**Vấn đề:** dự án nhỏ có nhiều lớp trung gian chỉ chuyển tiếp dữ liệu mà không tạo ranh giới hữu ích.

**Cách xử lý:** tách khi có khác biệt về trách nhiệm, vòng đời, hợp đồng hoặc khả năng thay thế. Một record và một service có thể đủ cho use case đơn giản.

## 22. Bài tập suy luận

**Câu 1.** `SendOrderConfirmationCommand` nên chứa `MimeMessage` hay `orderId`?

Thông thường chứa `orderId` và dữ liệu tối thiểu cần cho use case. `MimeMessage` là chi tiết hạ tầng được tạo ở gateway sau khi dữ liệu đã được xử lý.

**Câu 2.** `OrderMailView` và `Order` entity có nên là cùng một object?

Không nhất thiết. Entity phục vụ nghiệp vụ/persistence; view DTO chỉ mang các trường cần hiển thị. Tách DTO giúp tránh đưa dữ liệu nội bộ vào template.

**Câu 3.** Command và DTO có phải hai loại Java khác nhau?

Không. Cả hai có thể là record hoặc class. Command nhấn mạnh ý định hành động; DTO nhấn mạnh việc chuyển dữ liệu.

**Câu 4.** Client gửi `totalAmount` trong request. Có nên dùng giá trị đó trong email hóa đơn?

Chỉ khi hợp đồng nghiệp vụ thực sự cho phép và giá trị đã được xác minh. Thông thường tổng tiền phải lấy từ dữ liệu hóa đơn/domain có thẩm quyền.

**Câu 5.** Một service chỉ gửi email có ba trường. Có bắt buộc tạo request DTO, command, view DTO và rendered DTO riêng?

Không. Chỉ tách object khi chúng thể hiện các ranh giới có ý nghĩa. Không cần thêm abstraction không đem lại lợi ích.

**Câu 6.** `RenderedEmail` có nên chứa SMTP password?

Không. Nội dung đã render và thông tin xác thực SMTP thuộc trách nhiệm khác nhau. Credential được quản lý trong cấu hình hạ tầng/secret store.

**Câu 7.** Command được xử lý qua message queue và có thể redelivery. Cần nghĩ tới điều gì?

Idempotency, request ID, trạng thái job, retry và khả năng gửi trùng. Không nên giả định một command chỉ được thực hiện đúng một lần.

**Câu 8.** Có thể cho request truyền `templateName` rồi gọi template engine trực tiếp không?

Không nên nhận tên template tùy ý. Dùng loại thông báo/enum đã được allowlist và ánh xạ sang template cố định.

**Câu 9.** DTO có annotation `@Email` thì đã chứng minh địa chỉ nhận tồn tại chưa?

Chưa. Validator chỉ kiểm tra định dạng ở mức cú pháp; xác minh quyền sở hữu hoặc khả năng nhận thư cần quy trình khác.

**Câu 10.** Có nên lưu `Resource` hoặc `MimeMessage` vào database để worker gửi sau?

Thông thường không. Lưu định danh file, ID nghiệp vụ và dữ liệu command có thể serialize; worker resolve Resource và tạo MimeMessage khi xử lý.

## 23. Mô hình ghi nhớ

Khi thiết kế luồng gửi email, hãy đặt đúng object ở đúng ranh giới:

~~~mermaid
flowchart TD
    A["Request DTO / Event"] --> B["Command: ý định gửi"]
    B --> C["Application Service"]
    C --> D["Dữ liệu nghiệp vụ có thẩm quyền"]
    D --> E["Mail View DTO"]
    E --> F["Renderer"]
    F --> G["RenderedEmail"]
    G --> H["Mail Gateway"]
    H --> I["MimeMessageHelper"]
    I --> J["JavaMailSender"]
~~~

Các nguyên tắc cần nhớ:

1. **Command biểu diễn hành động**, ví dụ `SendOrderConfirmationCommand`; handler/service chịu trách nhiệm thực hiện.
2. **DTO mang dữ liệu qua ranh giới**, ví dụ request DTO, mail view DTO hoặc rendered content.
3. **Không tin dữ liệu client cho trạng thái, số tiền, quyền truy cập và template** nếu chúng phải do hệ thống quyết định.
4. **Dùng view DTO nhỏ** thay vì truyền entity hoặc application context vào template.
5. **Ưu tiên object bất biến** và defensive copy cho collection để dữ liệu không đổi giữa các bước.
6. **Giữ Spring Mail ở tầng gateway**; command không cần phụ thuộc `MimeMessage` hoặc `JavaMailSender`.
7. **Render plain text và HTML từ cùng snapshot/view model** để tránh hai representation mâu thuẫn.
8. **Attachment dùng định danh file được phân quyền**, không dùng filesystem path tùy ý từ request.
9. **Xử lý idempotency khi gửi bất đồng bộ hoặc retry**, tránh gửi trùng email.
10. **Không over-engineer**: chỉ tạo các object riêng khi chúng thể hiện hợp đồng hoặc trách nhiệm thực sự khác nhau.

Với ứng dụng nhỏ, một command cụ thể và một service gửi thư có thể đủ. Khi nhiều nghiệp vụ, template, provider hoặc kênh kích hoạt xuất hiện, việc phân tách command, view DTO, renderer và gateway giúp thay đổi cách gửi mà không làm rối logic nghiệp vụ. `JavaMailSender` vẫn chỉ là adapter gửi MIME qua SMTP; command và DTO giúp ứng dụng quyết định **gửi thư nào, cho ai, dựa trên dữ liệu nào và nội dung nào được phép hiển thị**.
