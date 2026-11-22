# Tách use case gửi mail khỏi lớp vận chuyển

Trong ứng dụng Spring, việc gửi email thường bắt đầu bằng một lời gọi ngắn đến JavaMailSender. Nhưng nếu controller, service nghiệp vụ hoặc use case tự tạo MimeMessage, cấu hình MimeMessageHelper và gọi trực tiếp JavaMailSender, logic ứng dụng đã phụ thuộc vào chi tiết vận chuyển email. Sau này muốn đổi SMTP provider, chuyển sang dịch vụ email qua HTTP API, gửi thông báo qua queue hoặc kiểm thử nghiệp vụ mà không có SMTP server, phần code nghiệp vụ sẽ phải thay đổi theo.

Cách tổ chức bền vững hơn là **để use case quyết định khi nào và vì sao cần gửi thông báo, còn adapter vận chuyển chịu trách nhiệm biến yêu cầu đó thành email MIME và chuyển tới nhà cung cấp**. Hai phần giao tiếp qua một interface (port) do ứng dụng định nghĩa. Adapter Spring Mail triển khai interface đó bằng JavaMailSender.

Sự phân tách này giúp use case tập trung vào quy tắc nghiệp vụ, giúp việc gửi mail có thể thay thế và kiểm thử độc lập, đồng thời giữ các kiểu của Spring Mail và Jakarta Mail ở lớp hạ tầng.

## 1. Vấn đề khi use case gọi trực tiếp JavaMailSender

Một service nghiệp vụ có thể được viết như sau:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final JavaMailSender mailSender;

    public OrderService(
            OrderRepository orderRepository,
            JavaMailSender mailSender) {
        this.orderRepository = orderRepository;
        this.mailSender = mailSender;
    }

    public void confirmOrder(Long orderId) throws MessagingException {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setTo(order.getCustomerEmail());
        helper.setSubject("Đơn hàng đã được xác nhận");
        helper.setText(
            "Đơn hàng " + order.getCode() + " đã được xác nhận.",
            "<h1>Đơn hàng đã được xác nhận</h1>"
                + "<p>Mã đơn: " + order.getCode() + "</p>"
        );

        mailSender.send(message);
    }
}
~~~

Đoạn code hoạt động, nhưng một class đang làm nhiều việc:

- Tải đơn hàng và thực hiện quy tắc xác nhận.
- Quyết định lúc nào cần gửi thông báo.
- Tạo subject và nội dung email.
- Xây dựng MIME message.
- Chọn multipart và charset.
- Phụ thuộc vào Spring Mail và Jakarta Mail.
- Gọi SMTP transport và xử lý lỗi vận chuyển.

Nếu đổi từ SMTP sang một nhà cung cấp có HTTP API, OrderService phải thay đổi. Nếu unit test confirmOrder, test phải mock các API tạo MIME hoặc phải dựng môi trường gửi mail. Nếu nhiều use case cùng gửi mail, logic tạo message có thể bị sao chép và dần không nhất quán.

Vấn đề chính là **quyết định nghiệp vụ đang nằm cùng chỗ với cách thực hiện việc gửi**.

## 2. Xác định trách nhiệm của từng lớp

Có thể chia luồng gửi mail thành các trách nhiệm sau:

| Thành phần | Trách nhiệm | Có nên phụ thuộc Spring Mail? |
| --- | --- | --- |
| Controller | Nhận yêu cầu HTTP, kiểm tra input và gọi use case | Không cần |
| Use case / application service | Thực hiện quy trình nghiệp vụ và quyết định khi nào cần thông báo | Không |
| Domain | Quy tắc và trạng thái nghiệp vụ | Không |
| Application port | Định nghĩa hợp đồng mà use case cần để gửi nội dung | Không |
| Content renderer | Tạo subject, plain text và HTML từ dữ liệu nghiệp vụ | Có thể nằm ở adapter riêng |
| SMTP adapter | Chuyển hợp đồng ứng dụng thành MIME message và gửi qua SMTP | Có |
| JavaMailSender | Thực hiện gửi thông qua cấu hình Spring Mail | Có |
| SMTP provider | Nhận message và xử lý tiếp theo chính sách nhà cung cấp | Ngoài ứng dụng |

Use case có thể nói: “Đơn hàng này đã được xác nhận; cần gửi nội dung xác nhận tới địa chỉ email của khách hàng.”

Adapter chịu trách nhiệm: “Tạo một MIME message UTF-8, đặt recipient, subject, text/HTML part, rồi gửi qua SMTP đã cấu hình.”

Use case không cần biết email được truyền bằng SMTP relay nào, cổng nào, TLS ra sao hoặc thư viện nào tạo MIME.

## 3. Luồng kiến trúc qua port và adapter

Trong kiến trúc Ports and Adapters (Hexagonal Architecture), use case gọi một interface hướng ra ngoài (outbound port). Adapter ở lớp hạ tầng triển khai interface đó.

~~~text
                 HTTP / UI
                    |
                    v
              Controller
                    |
                    v
             Application Use Case
                    |
          +---------+----------+
          |                    |
          v                    v
   OrderRepository       MailContentRenderer
       (port)                  (port)
          |                    |
          v                    v
   Database Adapter       Template Adapter
                               |
                               v
                         Rendered Mail
                               |
                               v
                         MailDeliveryPort
                               |
                               v
                      SmtpMailDeliveryAdapter
                               |
                               v
                         JavaMailSender
                               |
                               v
                         SMTP Provider
~~~

Các nguyên tắc:

1. Interface mà use case cần được định nghĩa ở application layer.
2. Use case phụ thuộc vào interface, không phụ thuộc implementation SMTP.
3. Adapter phụ thuộc vào application contract và thư viện vận chuyển.
4. Dependency source code hướng vào trong: infrastructure có thể biết application, application không biết infrastructure.
5. Thay adapter không làm thay đổi quy tắc nghiệp vụ nếu hợp đồng không đổi.

MailDeliveryPort là tên ví dụ. Có thể dùng tên khác như OutboundMailPort, EmailGateway hoặc NotificationDeliveryPort tùy quy ước dự án. Quan trọng là interface mô tả nhu cầu của application, không sao chép nguyên API của thư viện vận chuyển.

## 4. Thiết kế application port

Một port đơn giản có thể nhận một DTO độc lập với Spring:

~~~java
package com.example.application.port.out;

public interface MailDeliveryPort {
    void send(OutgoingMail mail);
}
~~~

DTO:

~~~java
package com.example.application.model;

public record OutgoingMail(
    String recipient,
    String subject,
    String plainText,
    String html
) {}
~~~

OutgoingMail là dữ liệu ứng dụng cần để chuyển một thông điệp. Nó không chứa MimeMessage, MimeMessageHelper, JavaMailSender, Session hay các kiểu của Jakarta Mail.

Có thể đặt contract và DTO trong package application:

~~~text
com.example
├── domain/
│   └── order/
├── application/
│   ├── usecase/
│   │   └── ConfirmOrderUseCase.java
│   ├── port/
│   │   └── out/
│   │       ├── MailDeliveryPort.java
│   │       ├── OrderRepository.java
│   │       └── OrderConfirmationRenderer.java
│   └── model/
│       └── OutgoingMail.java
└── infrastructure/
    └── mail/
        ├── SmtpMailDeliveryAdapter.java
        └── ThymeleafOrderConfirmationRenderer.java
~~~

Với ứng dụng nhỏ, không nhất thiết phải tạo nhiều module Maven/Gradle. Có thể bắt đầu bằng package boundary rõ ràng trong một module. Khi dự án lớn hơn, có thể tách application, domain và infrastructure thành module riêng để compiler giúp bảo vệ dependency direction.

### Chỉ đưa vào contract những gì use case cần

Nếu ứng dụng chỉ gửi email đơn giản, recipient, subject, plain text và HTML có thể đủ. Khi có yêu cầu thực tế, contract có thể mở rộng:

- From hoặc reply-to nếu nghiệp vụ cho phép chọn.
- Cc/Bcc nếu use case cần.
- Danh sách attachment với filename, media type và nguồn dữ liệu.
- Locale hoặc template identifier.
- Correlation ID để theo dõi.
- Idempotency key khi hệ thống có cơ chế chống gửi trùng.

Không nên đưa tất cả tính năng của SMTP/Jakarta Mail vào port chỉ để dự phòng. Hợp đồng quá rộng khiến use case vẫn phụ thuộc vào chi tiết vận chuyển, dù dependency được bọc trong một interface.

### Không để kiểu framework rò rỉ qua port

Tránh contract như:

~~~java
public interface MailDeliveryPort {
    void send(MimeMessage message);
}
~~~

hoặc:

~~~java
public interface MailDeliveryPort {
    void send(JavaMailSender sender, MimeMessageHelper helper);
}
~~~

Những kiểu này buộc application biết Jakarta Mail hoặc Spring Mail. Adapter không còn là nơi duy nhất chịu trách nhiệm chuyển đổi transport.

Tương tự, không nên để use case nhận MultipartFile từ Spring MVC làm attachment model. Hãy chuyển dữ liệu HTTP thành một application command hoặc file reference phù hợp trước khi gọi use case.

## 5. Tách phần tạo nội dung khỏi phần vận chuyển

Một email thường có hai công đoạn:

1. Tạo nội dung từ dữ liệu nghiệp vụ: subject, plain text, HTML, ngôn ngữ, template.
2. Chuyển nội dung thành message và gửi đi: MIME parts, headers, attachment, SMTP.

Hai công đoạn có thể được tách bằng một renderer port và một delivery port.

Renderer contract:

~~~java
package com.example.application.port.out;

public interface OrderConfirmationRenderer {
    OutgoingMail render(OrderConfirmationData data);
}
~~~

DTO đầu vào cho renderer:

~~~java
package com.example.application.model;

import java.math.BigDecimal;

public record OrderConfirmationData(
    String recipient,
    String customerName,
    String orderCode,
    BigDecimal totalAmount
) {}
~~~

Use case không cần biết nội dung được dựng bằng Thymeleaf, FreeMarker hay một template engine khác. Nó chỉ yêu cầu renderer tạo thông điệp theo dữ liệu đơn hàng.

Nếu dự án nhỏ, renderer có thể là một application service nội bộ thay vì port riêng. Chỉ tách thành port khi việc render thực sự cần thay thế, phụ thuộc vào template engine hoặc cần được kiểm thử độc lập.

## 6. Xây dựng use case gửi xác nhận đơn hàng

Ví dụ use case thực hiện các bước nghiệp vụ:

~~~java
package com.example.application.usecase;

import com.example.application.model.OrderConfirmationData;
import com.example.application.model.OutgoingMail;
import com.example.application.port.out.MailDeliveryPort;
import com.example.application.port.out.OrderConfirmationRenderer;
import com.example.application.port.out.OrderRepository;
import com.example.domain.order.Order;

public class ConfirmOrderUseCase {

    private final OrderRepository orderRepository;
    private final OrderConfirmationRenderer renderer;
    private final MailDeliveryPort mailDelivery;

    public ConfirmOrderUseCase(
            OrderRepository orderRepository,
            OrderConfirmationRenderer renderer,
            MailDeliveryPort mailDelivery) {
        this.orderRepository = orderRepository;
        this.renderer = renderer;
        this.mailDelivery = mailDelivery;
    }

    public void execute(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() ->
                new OrderNotFoundException(orderId));

        order.confirm();
        orderRepository.save(order);

        OrderConfirmationData data =
            new OrderConfirmationData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getCode(),
                order.getTotalAmount()
            );

        OutgoingMail mail = renderer.render(data);
        mailDelivery.send(mail);
    }
}
~~~

Use case tập trung vào quy trình: tìm đơn hàng, xác nhận, lưu trạng thái, tạo dữ liệu thông báo, render nội dung và yêu cầu gửi.

Nó không import bất kỳ class nào từ org.springframework.mail hoặc jakarta.mail.

### Lưu ý về transaction và thời điểm gửi

Ví dụ trên minh họa cách phân chia trách nhiệm, chưa phải cách triển khai tối ưu cho mọi hệ thống. Nếu orderRepository.save(order) chạy trong transaction và SMTP send xảy ra ngay sau đó, có thể có tình huống:

- SMTP nhận email thành công nhưng transaction database rollback.
- Transaction commit thành công nhưng SMTP lỗi hoặc timeout.
- Request bị retry và tạo email trùng.

Với thông báo không quan trọng hoặc ứng dụng đơn giản, gửi đồng bộ có thể chấp nhận được. Với thông báo giao dịch cần độ tin cậy cao, nên cân nhắc outbox pattern hoặc cơ chế gửi bất đồng bộ được quản lý.

## 7. Triển khai content renderer bằng Thymeleaf

Renderer adapter nhận DTO nghiệp vụ, render template và trả về contract trung lập.

~~~java
package com.example.infrastructure.mail;

import java.util.Locale;

import com.example.application.model.OrderConfirmationData;
import com.example.application.model.OutgoingMail;
import com.example.application.port.out.OrderConfirmationRenderer;

import org.springframework.stereotype.Component;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Component
public class ThymeleafOrderConfirmationRenderer
        implements OrderConfirmationRenderer {

    private final TemplateEngine templateEngine;

    public ThymeleafOrderConfirmationRenderer(
            TemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    @Override
    public OutgoingMail render(OrderConfirmationData data) {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderCode", data.orderCode());
        context.setVariable("totalAmount", data.totalAmount());

        String html = templateEngine.process(
            "mail/order-confirmation",
            context
        );

        String plainText = """
            Xin chào %s,

            Đơn hàng %s của bạn đã được xác nhận.
            Tổng tiền: %s
            """.formatted(
                data.customerName(),
                data.orderCode(),
                data.totalAmount()
            );

        return new OutgoingMail(
            data.recipient(),
            "Xác nhận đơn hàng " + data.orderCode(),
            plainText,
            html
        );
    }
}
~~~

Template HTML có thể nằm trong src/main/resources/templates/mail/order-confirmation.html:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Đơn hàng đã được xác nhận</h1>
  <p>Xin chào <strong th:text="${customerName}">Khách hàng</strong>,</p>
  <p>Mã đơn: <span th:text="${orderCode}">ORD-001</span></p>
  <p>Tổng tiền: <span th:text="${totalAmount}">0</span></p>
</body>
</html>
~~~

th:text escape nội dung text để dữ liệu động không bị hiểu thành markup. Nếu template tạo URL động, cần kiểm soát scheme và host được phép; HTML escaping tự nó không xác nhận URL là an toàn.

Renderer có thể được thay bằng FreeMarker hoặc template engine khác mà không sửa use case. Nếu nội dung email chỉ vài dòng và không cần template, có thể tạo nội dung trực tiếp trong một application service.

## 8. Triển khai SMTP adapter bằng JavaMailSender

SMTP adapter là nơi duy nhất trong luồng này cần biết Spring Mail và Jakarta Mail.

~~~java
package com.example.infrastructure.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import com.example.application.model.OutgoingMail;
import com.example.application.port.out.MailDeliveryPort;
import com.example.application.exception.MailDeliveryException;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class SmtpMailDeliveryAdapter implements MailDeliveryPort {

    private final JavaMailSender mailSender;

    public SmtpMailDeliveryAdapter(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public void send(OutgoingMail mail) {
        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(mail.plainText(), mail.html());

            mailSender.send(message);
        } catch (MessagingException | MailException exception) {
            throw new MailDeliveryException(
                "Could not submit email to the configured transport",
                exception
            );
        }
    }
}
~~~

Application exception:

~~~java
package com.example.application.exception;

public class MailDeliveryException extends RuntimeException {

    public MailDeliveryException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Adapter thực hiện chuyển đổi:

| Contract ứng dụng | MIME/Spring Mail |
| --- | --- |
| recipient | helper.setTo(...) |
| subject | helper.setSubject(...) |
| plainText và html | helper.setText(plainText, html) |
| MailDeliveryPort.send | JavaMailSender.send(message) |

Constructor MimeMessageHelper(message, true, "UTF-8") bật multipart và chỉ định encoding. Overload setText(plainText, html) tạo các phần alternative để email client có thể chọn bản phù hợp.

### Vì sao adapter chuyển exception?

MessagingException và MailException thuộc thư viện hạ tầng. Nếu chúng thoát qua use case, application lại biết chi tiết thư viện gửi mail.

Adapter chuyển lỗi sang MailDeliveryException của application. Lớp gọi use case có thể xử lý lỗi theo hợp đồng ổn định, còn adapter vẫn giữ exception gốc làm cause để log hoặc chẩn đoán.

Không nên bắt mọi exception rồi bỏ qua. Nếu SMTP submission thất bại mà use case vẫn báo thành công, hệ thống sẽ mất khả năng phát hiện thông báo chưa được gửi.

### Không nhầm accepted với delivered

Khi JavaMailSender.send(...) trả về bình thường, điều đó thường có nghĩa thao tác gửi tới transport/server đã hoàn tất theo hợp đồng của thư viện. Nó không chứng minh email đã vào Inbox, được người nhận đọc hoặc không bị bounce sau đó.

Nếu nghiệp vụ cần theo dõi trạng thái giao thư, cần tích hợp provider events/webhooks hoặc delivery status API và lưu trạng thái riêng. Không nên đặt tên kết quả của port là Delivered nếu adapter chỉ biết SMTP submission thành công.

## 9. Cấu hình SMTP chỉ nằm ở infrastructure

Thông tin host, port, credential và TLS thuộc cấu hình vận chuyển:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: MAIL_USERNAME
    password: MAIL_PASSWORD
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Các giá trị credential nên được cung cấp qua secret manager hoặc environment variables; không commit password vào source control.

Use case không cần đọc spring.mail.host, không biết port 587 và không tự bật STARTTLS. Các chi tiết đó được cấu hình cho adapter qua Spring Boot auto-configuration.

Nếu đổi provider, có thể tạo adapter mới:

~~~text
MailDeliveryPort
      |
      +--> SmtpMailDeliveryAdapter
      |
      +--> ProviderApiMailDeliveryAdapter
      |
      +--> LocalCaptureMailAdapter (test/dev)
~~~

Chỉ một implementation được đăng ký cho một profile/qualifier cụ thể trong runtime. Tránh để nhiều adapter cùng được component scan và cùng inject vào một port mà không có quy tắc chọn rõ ràng.

## 10. Đăng ký dependency và wiring

Spring có thể inject implementation qua constructor:

~~~java
@Configuration
public class MailConfiguration {

    @Bean
    public ConfirmOrderUseCase confirmOrderUseCase(
            OrderRepository orderRepository,
            OrderConfirmationRenderer renderer,
            MailDeliveryPort mailDeliveryPort) {
        return new ConfirmOrderUseCase(
            orderRepository,
            renderer,
            mailDeliveryPort
        );
    }
}
~~~

Nếu use case đã được đánh dấu @Service và các dependency được đăng ký thành bean, không cần khai báo @Bean thủ công. Hãy chọn một cách wiring nhất quán với dự án.

Ví dụ:

- OrderRepository có implementation database.
- OrderConfirmationRenderer được triển khai bởi ThymeleafOrderConfirmationRenderer.
- MailDeliveryPort được triển khai bởi SmtpMailDeliveryAdapter.
- ConfirmOrderUseCase chỉ nhận các abstraction cần thiết.

Dependency graph khi chạy:

~~~text
ConfirmOrderUseCase
   |
   +--> OrderRepository
   |       |
   |       +--> JpaOrderRepositoryAdapter
   |
   +--> OrderConfirmationRenderer
   |       |
   |       +--> ThymeleafOrderConfirmationRenderer
   |
   +--> MailDeliveryPort
           |
           +--> SmtpMailDeliveryAdapter
                    |
                    +--> JavaMailSender
~~~

Application không cần biết Spring container đã chọn implementation nào. Spring chỉ là cơ chế wiring adapter vào port.

## 11. Kiểm thử use case mà không cần SMTP server

Một lợi ích lớn của port là có thể thay SMTP adapter bằng fake trong unit test.

~~~java
class FakeMailDeliveryPort implements MailDeliveryPort {

    private final List<OutgoingMail> sent = new ArrayList<>();

    @Override
    public void send(OutgoingMail mail) {
        sent.add(mail);
    }

    public List<OutgoingMail> sentMessages() {
        return List.copyOf(sent);
    }
}
~~~

Test use case:

~~~java
@Test
void confirmingOrderRequestsConfirmationEmail() {
    FakeMailDeliveryPort mailDelivery = new FakeMailDeliveryPort();

    OrderConfirmationRenderer renderer = data ->
        new OutgoingMail(
            data.recipient(),
            "Xác nhận đơn hàng " + data.orderCode(),
            "Đơn hàng đã được xác nhận.",
            "<h1>Đơn hàng đã được xác nhận</h1>"
        );

    OrderRepository repository = new InMemoryOrderRepository(
        Order.pending("ORD-100", "customer@example.com")
    );

    ConfirmOrderUseCase useCase =
        new ConfirmOrderUseCase(repository, renderer, mailDelivery);

    useCase.execute(1L);

    assertEquals(1, mailDelivery.sentMessages().size());
    assertEquals(
        "customer@example.com",
        mailDelivery.sentMessages().get(0).recipient()
    );
}
~~~

Test này xác nhận use case yêu cầu gửi thông báo sau quy trình xác nhận. Nó không kiểm tra SMTP, TLS, MIME encoding hay email client. Các kiểm tra đó thuộc adapter/integration test.

### Kiểm thử khi gửi mail thất bại

Có thể tạo fake ném exception:

~~~java
MailDeliveryPort failingPort = mail -> {
    throw new MailDeliveryException(
        "Simulated mail transport failure",
        new RuntimeException("Connection refused")
    );
};
~~~

Sau đó kiểm tra use case hoặc application boundary xử lý lỗi theo yêu cầu. Với use case đồng bộ, lỗi có thể được truyền tới controller để trả phản hồi phù hợp. Với outbox/worker, lỗi thường được ghi nhận và xử lý theo retry policy.

## 12. Kiểm thử SMTP adapter riêng

SMTP adapter có trách nhiệm chuyển DTO thành MIME. Có thể kiểm thử nó độc lập bằng cách mock JavaMailSender và kiểm tra message được dựng đúng, hoặc dùng SMTP test server như GreenMail/MailHog trong integration test.

Những điểm nên kiểm tra ở adapter:

- Recipient và subject được gán đúng.
- Charset UTF-8 xử lý tiếng Việt.
- Plain text và HTML được tạo thành multipart/alternative.
- Attachment/inline resource được đóng gói đúng khi contract hỗ trợ chúng.
- Lỗi từ JavaMail/Spring Mail được chuyển thành application exception.
- Cấu hình TLS/auth được kiểm tra trong integration environment.

Unit test của use case không nên assert MIME boundary hay gọi MimeMessageHelper. Ngược lại, test adapter không cần xác nhận quy tắc nghiệp vụ như đơn hàng có được phép xác nhận hay không.

### Local capture adapter

Trong môi trường development, có thể thay adapter SMTP bằng adapter chỉ lưu email vào log/test mailbox hoặc một thư mục capture. Điều này giúp lập trình viên xem nội dung mà không gửi thư ra ngoài.

Một local adapter phải được chọn rõ bằng profile. Không để local capture vô tình được dùng trong production và cũng không để production SMTP credentials được tải vào môi trường test không cần thiết.

## 13. Khi nào nên dùng semantic notification port?

Không phải ứng dụng nào cũng cần một interface generic MailDeliveryPort. Nếu nghiệp vụ chỉ quan tâm đến một sự kiện cụ thể, có thể định nghĩa port theo ý nghĩa nghiệp vụ:

~~~java
public interface OrderConfirmationNotifier {
    void notifyOrderConfirmed(OrderConfirmationData data);
}
~~~

Use case:

~~~java
public class ConfirmOrderUseCase {

    private final OrderRepository orders;
    private final OrderConfirmationNotifier notifier;

    public void execute(Long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow();

        order.confirm();
        orders.save(order);

        notifier.notifyOrderConfirmed(
            new OrderConfirmationData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getCode(),
                order.getTotalAmount()
            )
        );
    }
}
~~~

Adapter email có thể triển khai port này bằng cách render template rồi gửi qua SMTP. Một adapter khác có thể gửi push notification hoặc gọi notification service bên ngoài.

So sánh hai lựa chọn:

| Port | Use case biết gì? | Phù hợp khi |
| --- | --- | --- |
| MailDeliveryPort | Có một thông điệp email đã được tạo và cần gửi | Application thực sự cần điều khiển nội dung mail hoặc nhiều use case dùng chung delivery contract |
| OrderConfirmationNotifier | Cần phát thông báo xác nhận đơn hàng | Nghiệp vụ chỉ quan tâm sự kiện/thông báo, kênh và nội dung là chi tiết triển khai |

Semantic port giúp application không bị ràng buộc vào khái niệm email nếu kênh có thể thay đổi. Generic mail port có ích khi email là một capability rõ ràng trong ứng dụng và nội dung đã được chuẩn hóa.

Không cần tạo cả hai lớp abstraction cho mọi use case. Chọn hợp đồng nhỏ nhất diễn đạt đúng nhu cầu của application.

## 14. Tách đồng bộ và bất đồng bộ

Gọi SMTP trực tiếp trong use case là gửi đồng bộ:

~~~text
HTTP request
    |
    v
Use case
    |
    v
JavaMailSender.send()
    |
    v
SMTP response
    |
    v
HTTP response
~~~

Ưu điểm:

- Luồng đơn giản.
- Lỗi submission có thể được trả về ngay.
- Dễ triển khai cho ứng dụng nhỏ.

Hạn chế:

- Request phải chờ network và SMTP server.
- SMTP chậm có thể kéo dài response time.
- Retry có thể làm request bị lặp.
- Lỗi SMTP có thể ảnh hưởng trải nghiệm thao tác nghiệp vụ.
- Transaction database và SMTP không cùng một transaction nguyên tử.

Với thông báo quan trọng, thường nên tách việc ghi nhận yêu cầu gửi khỏi việc thực sự chuyển message.

~~~text
HTTP request
    |
    v
Use case
    |
    +--> Update order
    |
    +--> Save notification/outbox record
    |
    v
Database commit
    |
    v
Background worker
    |
    v
MailDeliveryPort
    |
    v
SMTP adapter / provider
~~~

Use case ghi một outbox record trong cùng transaction với thay đổi nghiệp vụ. Worker đọc record sau khi commit, render nội dung và gửi qua port. Khi SMTP tạm lỗi, worker có thể retry mà không cần người dùng gửi lại request xác nhận đơn hàng.

## 15. Outbox pattern để tránh mất thông báo

Nếu ứng dụng chỉ commit đơn hàng rồi publish message sang queue ở một thao tác riêng, có thể xảy ra:

- Database commit thành công nhưng publish queue thất bại.
- Publish queue thành công nhưng database rollback.
- Worker nhận thông báo trước khi dữ liệu nghiệp vụ commit.

Outbox pattern giải quyết khoảng trống này bằng cách lưu event cần xử lý trong cùng transaction database với thay đổi nghiệp vụ.

Ví dụ bảng:

~~~sql
CREATE TABLE mail_outbox (
    id              BIGINT PRIMARY KEY,
    event_type      VARCHAR(120) NOT NULL,
    aggregate_id    VARCHAR(120) NOT NULL,
    payload         TEXT NOT NULL,
    status          VARCHAR(30) NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    created_at      TIMESTAMP NOT NULL,
    sent_at         TIMESTAMP NULL
);
~~~

Trong transaction xác nhận đơn hàng:

1. Cập nhật trạng thái order.
2. Insert một outbox record kiểu OrderConfirmed.
3. Commit cả hai cùng nhau.

Worker lấy record chưa xử lý, dựng dữ liệu thông báo, gọi MailDeliveryPort rồi cập nhật trạng thái. Nếu gửi thành công, đánh dấu hoàn tất. Nếu lỗi tạm thời, tăng attempts và lên lịch retry.

Outbox đảm bảo yêu cầu gửi không bị mất giữa database commit và enqueue. Nó **không tự bảo đảm email được gửi đúng một lần**. SMTP có thể nhận thư nhưng worker mất kết nối trước khi ghi trạng thái thành công; lần retry sau có thể tạo email trùng. Cần idempotency, delivery key hoặc đối soát provider nếu nghiệp vụ yêu cầu.

## 16. Thiết kế retry và phân loại lỗi

Không phải lỗi nào cũng nên retry giống nhau.

| Loại lỗi | Ví dụ | Cách xử lý thường dùng |
| --- | --- | --- |
| Tạm thời | Connection timeout, SMTP server unavailable, rate limit tạm thời | Retry với exponential backoff và jitter |
| Cấu hình | Credential sai, TLS cấu hình sai, host không hợp lệ | Dừng retry dày đặc, cảnh báo vận hành |
| Nội dung | Recipient sai định dạng, file quá lớn, template lỗi | Đánh dấu lỗi cần sửa dữ liệu/nội dung |
| Provider policy | Sender bị chặn, loại file không được phép | Không retry nguyên message; xử lý policy |
| Kết quả không rõ | Timeout sau khi SMTP DATA có thể đã được nhận | Đối soát delivery/provider event hoặc áp dụng idempotency |

Adapter có thể phân loại một số lỗi Spring/Jakarta thành exception ứng dụng có mã loại. Tuy nhiên, không nên phụ thuộc vào chuỗi thông báo lỗi tự do để quyết định retry. Nên dựa trên exception type, SMTP response code hoặc provider API code khi có thông tin đáng tin cậy.

Retry policy nên đặt ở worker/application orchestration, không nhét vòng lặp retry vào SmtpMailDeliveryAdapter. Adapter chịu trách nhiệm một lần thử gửi; worker quyết định lần tiếp theo khi nào.

## 17. Quản lý trạng thái gửi và idempotency

Một notification record có thể có các trạng thái:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- success ----> SUBMITTED
   |
   +---- transient --> RETRY_WAIT
   |
   +---- permanent --> FAILED
~~~

Tên trạng thái phải phản ánh điều hệ thống thực sự biết. Nếu SMTP adapter chỉ xác nhận submission, trạng thái nên là SUBMITTED hoặc ACCEPTED_BY_TRANSPORT, không phải DELIVERED.

Để giảm gửi trùng:

- Gán một notification ID ổn định.
- Dùng unique constraint cho event cần gửi một lần theo nghiệp vụ.
- Worker claim record bằng cơ chế lock/lease phù hợp.
- Lưu attempt ID và timestamp.
- Nếu provider hỗ trợ idempotency key, truyền key qua provider adapter.
- Nếu provider có delivery event, đối chiếu bằng provider message ID.

SMTP truyền thống không cung cấp idempotency semantics chung cho mọi server. Không thể tuyên bố exactly-once chỉ bằng cách thêm một cột status trong database.

## 18. Quản lý attachment mà không để lộ chi tiết Spring

Nếu use case cần attachment, contract nên mô tả dữ liệu mà application cần. Không đưa MultipartFile hoặc Resource vào application model.

Một lựa chọn là file reference:

~~~java
public record MailAttachment(
    String fileId,
    String fileName,
    String contentType
) {}
~~~

Application chỉ truyền file ID và metadata. Adapter hoặc một storage port khác chịu trách nhiệm lấy nội dung từ kho lưu trữ.

Nếu use case thực sự cần cung cấp bytes, có thể định nghĩa abstraction nội bộ:

~~~java
public interface AttachmentContent {
    InputStream openStream() throws IOException;
    long size();
}
~~~

Đây là một contract do ứng dụng định nghĩa; không dùng InputStreamResource hay FileSystemResource trong application layer.

Với file lớn, ưu tiên reference tới storage và stream có thể mở lại thay vì giữ toàn bộ bytes trong DTO. Hãy bảo đảm vòng đời file đủ dài cho tới khi worker gửi xong, và kiểm tra quyền truy cập trước khi đính kèm.

## 19. Không đưa thông tin vận chuyển vào domain model

Không thêm các field kiểu SMTP host, SMTP port, SMTP username/password, Jakarta MimeMessage, MIME boundary, SMTP response code hoặc TLS mode vào entity Order hoặc value object nghiệp vụ chỉ vì email cần chúng.

Domain có thể chứa địa chỉ email khách hàng nếu đó là dữ liệu nghiệp vụ. Nhưng việc tạo MIME message, chọn encoding, cấu hình transport và xử lý SMTP reply thuộc adapter/hạ tầng.

Ví dụ domain method:

~~~java
public void confirm() {
    if (status != OrderStatus.PENDING) {
        throw new IllegalStateException(
            "Only pending orders can be confirmed");
    }

    this.status = OrderStatus.CONFIRMED;
}
~~~

Domain không cần gọi mail sender. Use case quan sát kết quả nghiệp vụ rồi yêu cầu notification qua port.

## 20. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách tổ chức phù hợp |
| --- | --- | --- |
| Controller gọi trực tiếp JavaMailSender | HTTP layer biết chi tiết vận chuyển | Controller chỉ gọi use case |
| Domain entity tự gửi email | Domain phụ thuộc framework và side effect | Use case hoặc domain event kích hoạt port |
| Use case nhận MimeMessage | Jakarta Mail rò rỉ vào application | Dùng DTO/port do application định nghĩa |
| Mỗi service tự tạo MIME khác nhau | Nội dung và cấu hình không nhất quán | Dùng renderer và adapter dùng chung |
| Port sao chép toàn bộ API SMTP | Application vẫn phụ thuộc transport concept | Hợp đồng nhỏ theo nhu cầu |
| Adapter chứa quy tắc nghiệp vụ | Thay provider có thể thay đổi hành vi nghiệp vụ | Giữ policy trong use case/domain |
| Bắt lỗi gửi rồi log và bỏ qua | Use case báo thành công dù thông báo thất bại | Ném exception hoặc ghi trạng thái retry |
| Retry vô hạn trong adapter | Khó kiểm soát thời gian và gây gửi trùng | Retry ở worker với policy rõ ràng |
| Gọi SMTP trong transaction dài | Giữ database connection/lock trong lúc chờ network | Outbox và worker khi cần độ tin cậy |
| Gọi trạng thái SMTP accepted là delivered | Báo cáo delivery sai thực tế | Tách submission status khỏi delivery events |

## 21. Khi nào không cần tách quá nhiều lớp?

Không phải ứng dụng nào cũng cần một kiến trúc nhiều package và nhiều interface. Với một tiện ích nội bộ rất nhỏ, một service dùng trực tiếp JavaMailSender có thể đủ nếu không có yêu cầu thay provider hoặc test nghiệp vụ độc lập.

Nên tách port/adapter khi:

- Nhiều use case gửi email.
- Quy tắc nghiệp vụ cần test mà không phụ thuộc SMTP.
- Có nhiều môi trường hoặc provider.
- Cần local capture adapter.
- Gửi email là side effect quan trọng của transaction.
- Có nhu cầu chuyển sang queue, provider API hoặc kênh thông báo khác.
- Team muốn giữ application module không phụ thuộc Spring infrastructure.

Tránh tạo interface cho từng method chỉ để tăng số lượng abstraction. Một port có giá trị khi nó tạo ra ranh giới ổn định, có ý nghĩa và có khả năng thay thế implementation.

## 22. Quy trình triển khai từng bước

Có thể tách một service hiện tại theo thứ tự sau:

1. **Xác định use case**: thao tác nghiệp vụ nào cần phát thông báo và điều kiện gửi là gì?
2. **Định nghĩa contract**: tạo DTO và interface trong application layer, chỉ chứa dữ liệu mà use case cần.
3. **Tách nội dung**: chuyển template rendering ra renderer/service riêng nếu cần.
4. **Tạo adapter SMTP**: chuyển phần MimeMessageHelper, MimeMessage và JavaMailSender vào infrastructure.
5. **Map exception**: chuyển lỗi thư viện thành exception ứng dụng có ý nghĩa.
6. **Wiring bằng Spring**: inject adapter vào port qua constructor.
7. **Viết unit test use case**: dùng fake port để kiểm tra yêu cầu gửi và quy tắc nghiệp vụ.
8. **Viết adapter test**: kiểm tra MIME, encoding và hành vi SMTP bằng mock hoặc test server.
9. **Chọn mô hình đồng bộ/bất đồng bộ**: quyết định dựa trên yêu cầu response time, độ tin cậy và retry.
10. **Bổ sung outbox nếu cần**: lưu yêu cầu gửi cùng transaction và xử lý bằng worker.

Khi hoàn tất, luồng dependency nên có dạng:

~~~text
Application:
  ConfirmOrderUseCase
       |
       +--> OrderRepository (port)
       +--> OrderConfirmationRenderer (port)
       +--> MailDeliveryPort (port)

Infrastructure:
  JpaOrderRepositoryAdapter
  ThymeleafOrderConfirmationRenderer
  SmtpMailDeliveryAdapter
       |
       +--> JavaMailSender
       +--> MimeMessageHelper
       +--> SMTP provider
~~~

## 23. Ghi nhớ

Tách use case gửi mail khỏi lớp vận chuyển có nghĩa là giữ **quyết định nghiệp vụ** trong application và để **chi tiết MIME/SMTP** ở infrastructure:

- Use case quyết định khi nào cần gửi thông báo và dữ liệu nào liên quan.
- Application port mô tả hợp đồng gửi mà use case cần.
- DTO của application không phụ thuộc MimeMessage, MimeMessageHelper hoặc JavaMailSender.
- Renderer chịu trách nhiệm tạo subject, plain text và HTML từ dữ liệu nghiệp vụ.
- SMTP adapter chuyển contract thành MIME message và gọi JavaMailSender.
- Adapter chuyển lỗi Spring/Jakarta thành lỗi ứng dụng có ý nghĩa.
- Cấu hình host, port, credential và TLS nằm trong infrastructure/configuration.
- Unit test use case dùng fake port, không cần SMTP server.
- Integration test adapter kiểm tra MIME và transport riêng.
- Gửi đồng bộ phù hợp với luồng đơn giản; outbox/worker phù hợp khi cần độ tin cậy, retry và tách thời gian xử lý.
- SMTP accepted không đồng nghĩa email đã tới Inbox hoặc được đọc.
- Chọn port generic hoặc semantic theo đúng nhu cầu; không tạo abstraction dư thừa.

Khi use case chỉ phụ thuộc vào một contract ổn định, ứng dụng có thể thay SMTP adapter, đổi template engine hoặc dùng provider API mà không phải viết lại quy tắc xác nhận đơn hàng. Đây là lợi ích thực tế của việc tách use case gửi mail khỏi lớp vận chuyển trong Spring Framework Mail.
