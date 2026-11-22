# Nội dung email thay đổi theo trạng thái nghiệp vụ

## 1. Vì sao nội dung email cần phụ thuộc trạng thái nghiệp vụ?

Trong một ứng dụng, email thường là cách thông báo cho người dùng biết một sự kiện đã xảy ra hoặc họ cần thực hiện bước tiếp theo. Cùng một đối tượng nghiệp vụ có thể đi qua nhiều trạng thái trong vòng đời của nó. Ví dụ, một đơn hàng có thể lần lượt ở các trạng thái **Chờ thanh toán**, **Đã xác nhận**, **Đang giao**, **Đã giao**, **Đã hủy** hoặc **Hoàn tiền**.

Mỗi trạng thái có ý nghĩa khác nhau, nên email gửi đi cũng cần thay đổi:

- Khi đơn hàng được tạo, người mua cần biết mã đơn và cách thanh toán.
- Khi thanh toán được xác nhận, người mua cần biết đơn đã được tiếp nhận.
- Khi đơn hàng được giao cho đơn vị vận chuyển, người mua cần biết mã theo dõi.
- Khi giao hàng hoàn tất, người mua có thể cần xác nhận đã nhận hàng hoặc xem hướng dẫn hỗ trợ.
- Khi đơn bị hủy, người mua cần biết lý do và tình trạng hoàn tiền nếu có.

Nếu mọi lần gửi đều dùng một subject và body chung như “Đơn hàng của bạn đã được cập nhật”, người nhận sẽ không hiểu thay đổi nào vừa xảy ra và cần làm gì tiếp theo. Ngược lại, nếu nội dung được tạo từ trạng thái nghiệp vụ, email có thể truyền đạt chính xác **sự kiện, thông tin liên quan, hành động kế tiếp và người nhận phù hợp**.

Trong **Spring Framework Mail**, **JavaMailSender** và **MimeMessageHelper** chịu trách nhiệm tạo và gửi thông điệp. Quyết định **gửi email nào, khi nào gửi, cho ai và nội dung nào tương ứng với trạng thái nào** thuộc về logic ứng dụng.

Một luồng khái quát:

~~~text
Người dùng / hệ thống bên ngoài
              |
              v
       Lệnh nghiệp vụ
              |
              v
     Kiểm tra transition
              |
              v
       Cập nhật trạng thái
              |
              v
       Tạo notification event
              |
              v
       Chọn nội dung email
              |
       +------+------+
       |             |
       v             v
   Plain text       HTML
       |             |
       +------+------+
              |
              v
       MimeMessageHelper
              |
              v
        JavaMailSender
              |
              v
             SMTP
~~~

Điểm quan trọng: **trạng thái nghiệp vụ là dữ liệu đầu vào để quyết định nội dung**, còn việc gửi email là một tác vụ thông báo có vòng đời và lỗi riêng.

## 2. Trạng thái nghiệp vụ và sự kiện chuyển trạng thái

Trạng thái (*state*) mô tả tình trạng hiện tại của một đối tượng. Sự kiện chuyển trạng thái (*state transition*) mô tả việc đối tượng thay đổi từ trạng thái cũ sang trạng thái mới do một hành động hoặc kết quả xử lý.

Ví dụ vòng đời đơn hàng:

~~~text
                 +-------------------+
                 |      CREATED      |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | PENDING_PAYMENT   |
                 +---------+---------+
                           |
                  Thanh toán thành công
                           |
                           v
                 +-------------------+
                 |       PAID        |
                 +---------+---------+
                           |
                     Đóng gói xong
                           |
                           v
                 +-------------------+
                 |      SHIPPED      |
                 +---------+---------+
                           |
                     Giao thành công
                           |
                           v
                 +-------------------+
                 |     DELIVERED     |
                 +-------------------+

Các nhánh khác:
PENDING_PAYMENT -> CANCELLED
PAID -> CANCELLED (nếu chính sách cho phép)
PAID -> REFUND_PENDING -> REFUNDED
~~~

Sơ đồ chỉ là ví dụ. Một ứng dụng thực tế phải định nghĩa transition hợp lệ theo quy tắc nghiệp vụ của chính nó.

### State không đồng nghĩa event

Giả sử đơn hàng đang ở trạng thái **SHIPPED**. Một lần người dùng mở trang chi tiết, một lần cập nhật ghi chú nội bộ hoặc một lần đồng bộ dữ liệu có thể lưu lại bản ghi mà trạng thái vẫn là SHIPPED. Không phải mỗi lần lưu đều có nghĩa “đơn hàng vừa được gửi đi”.

Phân biệt:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Current state** | Đối tượng hiện ở tình trạng nào? | order.status = SHIPPED |
| **Transition** | Nó vừa chuyển từ đâu sang đâu? | PAID -> SHIPPED |
| **Business event** | Điều gì vừa xảy ra? | OrderShipped |
| **Notification** | Có cần thông báo cho ai không? | Gửi email có mã theo dõi |

Nếu chỉ đọc trạng thái hiện tại rồi gửi email mỗi lần entity được lưu, ứng dụng có thể gửi trùng thông báo. Cách tốt hơn là tạo notification dựa trên **transition hoặc business event đã được xác nhận**.

## 3. Xác định nội dung theo từng trạng thái

Trước khi viết code, hãy lập bảng mapping giữa trạng thái, sự kiện, người nhận và thông tin cần truyền tải.

Ví dụ cho vòng đời đơn hàng:

| Trạng thái / sự kiện | Người nhận thường gặp | Subject minh họa | Nội dung chính |
|---|---|---|---|
| PENDING_PAYMENT | Người mua | Xác nhận đơn hàng và hướng dẫn thanh toán | Mã đơn, số tiền, hạn thanh toán, link thanh toán |
| PAID | Người mua | Đã nhận thanh toán cho đơn hàng | Mã đơn, số tiền đã thanh toán, bước tiếp theo |
| PROCESSING | Người mua | Đơn hàng đang được chuẩn bị | Trạng thái xử lý và thời gian dự kiến nếu có |
| SHIPPED | Người mua | Đơn hàng đã được gửi đi | Đơn vị vận chuyển, mã tracking, link theo dõi |
| DELIVERED | Người mua | Đơn hàng đã được giao | Thời điểm giao, hướng dẫn hỗ trợ hoặc đánh giá |
| CANCELLED | Người mua; đôi khi bộ phận vận hành | Đơn hàng đã bị hủy | Lý do, số tiền và trạng thái hoàn tiền |
| REFUND_PENDING | Người mua | Yêu cầu hoàn tiền đang được xử lý | Số tiền, thời gian dự kiến, kênh hoàn |
| REFUNDED | Người mua | Đã hoàn tiền | Số tiền, mã tham chiếu, thời điểm hoàn |

Không phải trạng thái nào cũng cần email. Ví dụ một trạng thái kỹ thuật như **RETRYING_PAYMENT_PROVIDER** có thể chỉ cần log hoặc metric nội bộ. Email nên dành cho thay đổi có ý nghĩa với người nhận.

### Một trạng thái có thể tạo nhiều loại thông báo

Ví dụ khi đơn chuyển sang SHIPPED:

- Người mua nhận email có tracking number.
- Nhân viên hỗ trợ có thể nhận thông báo nội bộ nếu đơn thuộc nhóm cần theo dõi.
- Hệ thống vận hành có thể ghi event hoặc metric mà không gửi email.

Do đó, không nên gắn cứng “một status tương ứng một email duy nhất”. Cần xác định **event + audience + notification purpose**.

## 4. Thiết kế quy tắc transition trước khi gửi email

Ứng dụng cần xác định những chuyển trạng thái hợp lệ. Nếu người dùng hoặc một integration gửi yêu cầu sai thứ tự, không nên phát email như thể hành động đã thành công.

Ví dụ:

| Trạng thái hiện tại | Trạng thái yêu cầu | Có thể hợp lệ? | Lý do |
|---|---|---|---|
| PENDING_PAYMENT | PAID | Có | Cổng thanh toán xác nhận thành công |
| PENDING_PAYMENT | CANCELLED | Có | Người mua hoặc hệ thống hủy theo chính sách |
| PAID | SHIPPED | Có | Đơn đã được bàn giao cho vận chuyển |
| SHIPPED | DELIVERED | Có | Có xác nhận giao hàng |
| DELIVERED | PENDING_PAYMENT | Không | Không phải transition hợp lệ trong vòng đời này |
| CANCELLED | SHIPPED | Thường không | Đơn đã hủy không nên tiếp tục giao nếu không có quy trình khôi phục riêng |

Không cập nhật status bằng một phép gán tùy tiện từ request:

~~~java
// Không nên để request quyết định trực tiếp mọi trạng thái.
order.setStatus(request.status());
orderRepository.save(order);
~~~

Thay vào đó, đưa thay đổi qua phương thức nghiệp vụ:

~~~java
public void markShipped(String orderId, String trackingNumber) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.markShipped(trackingNumber);
    orderRepository.save(order);
}
~~~

Phương thức **Order.markShipped(...)** cần kiểm tra trạng thái hiện tại, điều kiện thanh toán, thông tin vận chuyển và quy tắc chuyển trạng thái. Chỉ sau khi transition hợp lệ, ứng dụng mới tạo event thông báo.

## 5. Mô hình hóa trạng thái bằng enum

Với một vòng đời có tập trạng thái hữu hạn, Java enum giúp tránh chuỗi tùy ý:

~~~java
public enum OrderStatus {
    PENDING_PAYMENT,
    PAID,
    PROCESSING,
    SHIPPED,
    DELIVERED,
    CANCELLED,
    REFUND_PENDING,
    REFUNDED
}
~~~

Không nên lưu các nhãn hiển thị như “Đã giao hàng” trực tiếp làm giá trị trạng thái nội bộ. Dùng mã ổn định như DELIVERED, sau đó ánh xạ sang nội dung hiển thị theo ngôn ngữ và ngữ cảnh.

Một transition có thể được biểu diễn:

~~~java
public record OrderStatusChanged(
        String orderId,
        OrderStatus previousStatus,
        OrderStatus currentStatus,
        Instant occurredAt
) {
}
~~~

Event chứa trạng thái cũ, trạng thái mới và thời điểm thay đổi. Với notification cần snapshot dữ liệu, có thể bổ sung các trường cần thiết như mã đơn, recipient, tracking number hoặc URL nghiệp vụ đã được kiểm tra.

## 6. Dùng switch để chọn nội dung theo trạng thái

Với số trạng thái nhỏ và logic đơn giản, Java switch expression là cách dễ đọc:

~~~java
public EmailContent contentFor(OrderStatus status) {
    return switch (status) {
        case PENDING_PAYMENT -> new EmailContent(
                "Xác nhận đơn hàng",
                "Đơn hàng đang chờ thanh toán."
        );
        case PAID -> new EmailContent(
                "Đã nhận thanh toán",
                "Chúng tôi đã nhận được thanh toán cho đơn hàng."
        );
        case PROCESSING -> new EmailContent(
                "Đơn hàng đang được chuẩn bị",
                "Đơn hàng của bạn đang được xử lý."
        );
        case SHIPPED -> new EmailContent(
                "Đơn hàng đã được gửi đi",
                "Đơn hàng đã được bàn giao cho đơn vị vận chuyển."
        );
        case DELIVERED -> new EmailContent(
                "Đơn hàng đã được giao",
                "Đơn hàng đã được giao đến địa chỉ nhận."
        );
        case CANCELLED -> new EmailContent(
                "Đơn hàng đã bị hủy",
                "Đơn hàng đã được hủy theo yêu cầu hoặc chính sách."
        );
        case REFUND_PENDING -> new EmailContent(
                "Yêu cầu hoàn tiền đang được xử lý",
                "Chúng tôi đang xử lý yêu cầu hoàn tiền."
        );
        case REFUNDED -> new EmailContent(
                "Đã hoàn tiền",
                "Khoản tiền đã được hoàn theo phương thức thanh toán."
        );
    };
}
~~~

EmailContent có thể là một record:

~~~java
public record EmailContent(String subject, String body) {
}
~~~

Ưu điểm của switch expression trên enum là compiler có thể giúp phát hiện trường hợp chưa xử lý khi thêm một enum value mới, nếu không có nhánh default. Tuy nhiên, khi ứng dụng có nhiều ngôn ngữ, nhiều loại người nhận, nhiều template hoặc nhiều kênh thông báo, một switch lớn sẽ khó bảo trì. Khi đó nên tách mapping thành các thành phần chuyên biệt.

## 7. Tách nội dung email khỏi logic chuyển trạng thái

Không nên đặt toàn bộ subject, HTML và chi tiết SMTP trực tiếp trong entity nghiệp vụ. Entity cần bảo vệ quy tắc trạng thái; dịch vụ notification chịu trách nhiệm tạo nội dung và gửi.

Một cách chia trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| Order | Trạng thái và transition hợp lệ |
| OrderApplicationService | Điều phối hành động nghiệp vụ |
| OrderStatusChanged | Ghi nhận sự kiện transition |
| EmailContentResolver | Chọn nội dung theo event và audience |
| EmailTemplateRenderer | Render plain text và HTML |
| MailNotificationService | Tạo MimeMessage và gọi JavaMailSender |
| NotificationRepository / outbox | Lưu ý định gửi, trạng thái xử lý và attempt |

Luồng:

~~~text
OrderApplicationService
        |
        v
Order.markShipped(...)
        |
        v
OrderStatusChanged
        |
        v
EmailContentResolver
        |
        v
TemplateRenderer
        |
        v
MailNotificationService
        |
        v
JavaMailSender
~~~

Cách chia này giúp thay đổi wording hoặc template mà không sửa quy tắc transition, đồng thời giúp kiểm tra nội dung email mà không cần kết nối SMTP.

## 8. Tạo dữ liệu notification từ snapshot nghiệp vụ

Email thường cần dữ liệu tại thời điểm sự kiện xảy ra. Nếu worker chỉ nhận orderId, sau đó truy vấn trạng thái hiện tại khi gửi, nội dung có thể không còn khớp với event ban đầu.

Ví dụ:

1. Đơn chuyển từ PAID sang SHIPPED.
2. Hệ thống tạo notification “Đơn đã gửi đi”.
3. Email bị đưa vào queue.
4. Trước khi worker xử lý, đơn đã chuyển sang DELIVERED.
5. Worker đọc current state và render email “Đã giao hàng”.

Người nhận có thể nhận thông báo giao hàng trước thông báo đã gửi đi hoặc không nhận được thông tin tracking như mong muốn.

### Snapshot event

Một event có thể giữ dữ liệu cần thiết tại thời điểm transition:

~~~java
public record OrderShippedEvent(
        String orderId,
        String orderCode,
        String recipientEmail,
        String customerName,
        String trackingNumber,
        String trackingUrl,
        Instant shippedAt
) {
}
~~~

Worker dùng snapshot này để tạo nội dung thông báo về sự kiện OrderShipped. Nếu dữ liệu cần được xác thực hoặc thay đổi theo quyền tại thời điểm gửi, worker có thể truy vấn bổ sung, nhưng phải giữ rõ event gốc và quy tắc snapshot.

Không nên nhét toàn bộ entity vào event. Chỉ giữ các trường cần cho notification, hoặc giữ ID cùng version/snapshot có thể truy xuất nhất quán. Cần cân nhắc dữ liệu cá nhân trong event và outbox vì chúng có thể được lưu lâu hơn request ban đầu.

## 9. Ví dụ: chọn nội dung cho từng trạng thái đơn hàng

Có thể định nghĩa một model cho dữ liệu email:

~~~java
public record OrderEmailData(
        String customerName,
        String orderCode,
        OrderStatus status,
        BigDecimal totalAmount,
        String currency,
        String trackingNumber,
        String trackingUrl,
        String nextActionUrl
) {
}
~~~

Một resolver trả về nội dung text/HTML dựa trên event:

~~~java
public record RenderedEmail(
        String subject,
        String plainText,
        String htmlText
) {
}

public interface OrderEmailContentResolver {
    RenderedEmail resolve(OrderEmailData data);
}
~~~

Triển khai đơn giản:

~~~java
public class DefaultOrderEmailContentResolver
        implements OrderEmailContentResolver {

    @Override
    public RenderedEmail resolve(OrderEmailData data) {
        return switch (data.status()) {
            case PENDING_PAYMENT -> pendingPayment(data);
            case PAID -> paid(data);
            case PROCESSING -> processing(data);
            case SHIPPED -> shipped(data);
            case DELIVERED -> delivered(data);
            case CANCELLED -> cancelled(data);
            case REFUND_PENDING -> refundPending(data);
            case REFUNDED -> refunded(data);
        };
    }

    private RenderedEmail shipped(OrderEmailData data) {
        String subject = "Đơn hàng " + data.orderCode() + " đã được gửi đi";
        String plain = """
                Xin chào %s,

                Đơn hàng %s đã được bàn giao cho đơn vị vận chuyển.
                Mã theo dõi: %s
                Theo dõi: %s
                """.formatted(
                data.customerName(),
                data.orderCode(),
                data.trackingNumber(),
                data.trackingUrl()
        );

        String html = """
                <html lang="vi">
                  <body>
                    <h1>Đơn hàng đã được gửi đi</h1>
                    <p>Xin chào!</p>
                    <p>Mã đơn hàng: <strong>%s</strong></p>
                    <p>Mã theo dõi: <strong>%s</strong></p>
                    <p><a href="%s">Theo dõi đơn hàng</a></p>
                  </body>
                </html>
                """.formatted(
                escapeHtml(data.orderCode()),
                escapeHtml(data.trackingNumber()),
                escapeHtmlAttribute(data.trackingUrl())
        );

        return new RenderedEmail(subject, plain, html);
    }

    // Các phương thức pendingPayment, paid, processing, delivered,
    // cancelled, refundPending và refunded được triển khai tương tự.
}
~~~

Đây là ví dụ cấu trúc. Các hàm escapeHtml và escapeHtmlAttribute đại diện cho việc escape theo ngữ cảnh bằng thư viện hoặc template engine phù hợp; chúng không phải API có sẵn của Spring Mail. trackingUrl phải được tạo từ domain được phép và xác minh trước khi render.

Nếu resolver phải xử lý mọi trạng thái, cần triển khai đủ các nhánh. Có thể chia nhỏ thành các renderer riêng để tránh một class quá lớn.

## 10. Gửi email bằng JavaMailSender và MimeMessageHelper

Sau khi nội dung được chọn và render, dịch vụ gửi mail không cần biết quy tắc chuyển trạng thái. Nó chỉ nhận người nhận, subject, plain text và HTML.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailNotificationService {

    private final JavaMailSender mailSender;

    public MailNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            RenderedEmail content
    ) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject(content.subject());
        helper.setText(content.plainText(), content.htmlText());

        mailSender.send(message);
    }
}
~~~

Ví dụ giả định ứng dụng đã cấu hình JavaMailSender và địa chỉ From được SMTP provider cho phép. **setText(plainText, htmlText)** cung cấp hai biểu diễn thay thế; nó không tự tạo nội dung theo trạng thái. Resolver đã quyết định nội dung trước khi gọi dịch vụ gửi.

### Cấu hình Spring Boot minh họa

Dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

SMTP submission qua STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

Host và credential là giá trị minh họa. Trong production, lấy bí mật từ biến môi trường hoặc secret manager, không commit password thật. Port và TLS phải phù hợp với nhà cung cấp SMTP.

## 11. Không gửi email chỉ vì entity được lưu

Một anti-pattern là gửi email ngay trong setter hoặc callback mỗi khi status thay đổi:

~~~java
public void setStatus(OrderStatus status) {
    this.status = status;
    mailSender.send(...); // Không nên đặt side effect ở entity.
}
~~~

Cách này có nhiều vấn đề:

- Entity bị phụ thuộc vào hạ tầng email.
- Có thể gửi trước khi transaction database commit.
- ORM có thể gọi setter khi hydrate entity hoặc cập nhật dữ liệu.
- Test logic nghiệp vụ phải mock SMTP.
- Không kiểm soát được retry, duplicate và trạng thái gửi.
- Một lần save không nhất thiết tương ứng một transition có ý nghĩa với người dùng.

Nên phát event hoặc tạo outbox record từ application service sau khi xác nhận transition hợp lệ.

## 12. Transaction và thời điểm gửi email

Giả sử một service vừa cập nhật đơn hàng vừa gửi email:

~~~java
@Transactional
public void markShipped(String orderId) {
    Order order = orderRepository.findById(orderId).orElseThrow();
    order.markShipped();
    orderRepository.save(order);

    mailSender.send(...);
}
~~~

Đoạn này có rủi ro: SMTP có thể chấp nhận email nhưng transaction database sau đó rollback. Người dùng nhận email “đã gửi hàng” trong khi database vẫn ghi trạng thái cũ. Chiều ngược lại, nếu database commit nhưng SMTP lỗi, trạng thái đã thay đổi nhưng email chưa được gửi.

### Phương án đơn giản: gửi sau khi transaction commit

Spring hỗ trợ **@TransactionalEventListener** để xử lý application event theo phase của transaction:

~~~java
public record OrderShippedEvent(
        String orderId,
        String recipientEmail,
        String orderCode,
        String trackingNumber,
        String trackingUrl
) {
}
~~~

Phát event trong service nghiệp vụ:

~~~java
@Transactional
public void markShipped(String orderId, ShipmentInfo shipment) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.markShipped(shipment);
    orderRepository.save(order);

    eventPublisher.publishEvent(new OrderShippedEvent(
            order.getId(),
            order.getCustomerEmail(),
            order.getCode(),
            shipment.trackingNumber(),
            shipment.trackingUrl()
    ));
}
~~~

Listener:

~~~java
@Component
public class OrderMailListener {

    private final OrderEmailFacade emailFacade;

    public OrderMailListener(OrderEmailFacade emailFacade) {
        this.emailFacade = emailFacade;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderShipped(OrderShippedEvent event) {
        emailFacade.sendShipped(event);
    }
}
~~~

AFTER_COMMIT giúp listener chỉ chạy sau khi transaction đã commit. Tuy nhiên, listener trong bộ nhớ **không phải durable queue**. Nếu tiến trình dừng sau commit nhưng trước khi listener gửi, event có thể mất. Nếu gửi mail lỗi, ứng dụng cũng cần cơ chế ghi nhận và retry riêng.

### Phương án đáng tin cậy hơn: transactional outbox

Với thông báo quan trọng, có thể lưu notification/outbox record trong cùng transaction database với thay đổi trạng thái:

~~~text
Transaction database
    |
    +--> UPDATE order status = SHIPPED
    |
    +--> INSERT notification_outbox
              event_type = ORDER_SHIPPED
              aggregate_id = orderId
              payload = snapshot cần gửi
              status = PENDING
    |
    +--> COMMIT
             |
             v
      Background worker đọc outbox
             |
             v
      Render nội dung theo event
             |
             v
      JavaMailSender.send(...)
             |
             v
      Ghi trạng thái SENT / RETRY / FAILED
~~~

Nhờ vậy, thay đổi trạng thái và ý định gửi notification được commit cùng nhau. Worker có thể xử lý lại các record còn pending sau khi ứng dụng khởi động lại.

Outbox không tự bảo đảm gửi đúng một lần. Worker có thể gửi thành công rồi chết trước khi cập nhật SENT; lần sau nó có thể gửi lại. Cần idempotency, attempt tracking và cách đối soát phù hợp.

## 13. Chống gửi trùng bằng event identity và idempotency

Một trạng thái có thể được cập nhật lặp lại bởi webhook, job retry hoặc request gửi lại. Nếu mỗi lần xử lý đều phát notification, người nhận có thể nhận nhiều email giống nhau.

Mỗi sự kiện nên có một định danh ổn định:

~~~java
public record NotificationEvent(
        UUID eventId,
        String aggregateId,
        String eventType,
        Instant occurredAt
) {
}
~~~

Trước khi tạo hoặc gửi email, hệ thống có thể bảo đảm một notification key chỉ được xử lý một lần ở mức nghiệp vụ:

~~~text
notification key:
  orderId + eventType + transitionVersion

Ví dụ:
  ORD-123 + ORDER_SHIPPED + version 7
~~~

Không nên chỉ dùng orderId + status nếu một đối tượng có thể hợp lệ quay lại cùng trạng thái trong các chu kỳ khác nhau. Version hoặc event ID giúp phân biệt các lần transition.

Một bảng outbox/notification có thể có unique constraint trên khóa nghiệp vụ. Điều này ngăn hai request đồng thời tạo hai notification giống nhau khi cùng xử lý một transition.

**Idempotency ở database không đồng nghĩa exactly-once delivery qua SMTP.** SMTP không cung cấp giao dịch phân tán cùng database để bảo đảm cả hai hệ thống commit nguyên tử. Cần chấp nhận và quản lý khả năng gửi trùng trong tình huống kết quả không rõ.

## 14. Xử lý retry và trạng thái gửi

Không phải lỗi gửi email nào cũng nên retry theo cùng cách:

| Kết quả | Hướng xử lý |
|---|---|
| SMTP tạm thời từ chối hoặc timeout trước khi nộp dữ liệu | Có thể retry với backoff và giới hạn số lần |
| Sai credential hoặc thiếu quyền gửi | Sửa cấu hình/quyền; retry liên tục không có ích |
| Địa chỉ recipient không hợp lệ | Sửa dữ liệu hoặc đánh dấu lỗi nghiệp vụ |
| Nội dung/template lỗi | Sửa renderer/template trước khi thử lại |
| Timeout sau khi server có thể đã nhận DATA | Trạng thái chưa rõ; đối soát trước khi gửi lại |
| SMTP chấp nhận nhưng bounce về sau | Xử lý delivery event/bounce theo provider |

Có thể lưu trạng thái notification:

~~~java
public enum NotificationStatus {
    PENDING,
    PROCESSING,
    SENT_TO_PROVIDER,
    RETRY,
    FAILED,
    UNKNOWN
}
~~~

Tên SENT_TO_PROVIDER diễn tả rõ hơn DELIVERED: lời gọi gửi thành công thường chỉ cho biết SMTP/provider đã chấp nhận ở chặng nộp thư, không chứng minh thư đã vào Inbox.

Một record notification có thể giữ:

- Event ID và khóa idempotency.
- Recipient đã được xác thực.
- Template key và locale.
- Payload/snapshot cần render.
- Số lần thử và thời điểm thử gần nhất.
- Provider response hoặc message ID nếu có.
- Lỗi đã được làm sạch để lưu log.

Không lưu token hoặc toàn bộ nội dung nhạy cảm lâu hơn cần thiết. Cần áp dụng retention và quyền truy cập cho bảng outbox.

## 15. Nội dung khác nhau theo người nhận và vai trò

Không chỉ status quyết định email. Cùng một event có thể cần nội dung khác nhau cho các audience:

| Event | Người mua | Nhân viên vận hành |
|---|---|---|
| ORDER_PAID | Đã nhận thanh toán, bước tiếp theo | Thanh toán thành công, cần xử lý đơn |
| ORDER_SHIPPED | Mã tracking và link theo dõi | Đơn đã bàn giao, thông tin hãng vận chuyển |
| ORDER_CANCELLED | Lý do hủy và hoàn tiền | Người thực hiện, nguyên nhân, dữ liệu audit |

Vì vậy, khóa lựa chọn template có thể gồm:

~~~text
eventType + audience + locale + channel
~~~

Ví dụ:

~~~text
ORDER_SHIPPED + CUSTOMER + vi-VN + EMAIL
ORDER_SHIPPED + OPERATIONS + en-US + EMAIL
~~~

Không nên gửi cùng một body nội bộ cho khách hàng nếu body có ghi chú vận hành, dữ liệu rủi ro hoặc thông tin không được phép công khai.

### Xác định recipient từ nghiệp vụ

Địa chỉ người nhận phải được lấy từ nguồn đã xác thực và có quyền nhận thông báo. Không tin email tùy ý được truyền trong payload webhook nếu webhook không được xác minh. Với thông báo cho khách hàng, cần xác định email đang có hiệu lực và trạng thái consent theo loại thư.

## 16. Subject, nội dung và hành động nên khớp trạng thái

Email cần nói rõ:

1. **Điều gì đã xảy ra?**
2. **Đối tượng nào bị ảnh hưởng?**
3. **Người nhận cần biết thông tin nào?**
4. **Bước tiếp theo là gì, nếu có?**
5. **Liên kết nào mở đúng hành động?**

Ví dụ:

| Trạng thái | Subject rõ ràng | CTA phù hợp |
|---|---|---|
| PENDING_PAYMENT | Đơn hàng đang chờ thanh toán | Thanh toán đơn hàng |
| PAID | Đã nhận thanh toán cho đơn hàng | Xem đơn hàng |
| SHIPPED | Đơn hàng đã được gửi đi | Theo dõi vận chuyển |
| DELIVERED | Đơn hàng đã được giao | Xem chi tiết / Nhận hỗ trợ |
| CANCELLED | Đơn hàng đã bị hủy | Xem thông tin hoàn tiền |
| REFUNDED | Đã hoàn tiền cho đơn hàng | Xem chi tiết giao dịch |

Không hiển thị CTA không còn hợp lệ. Ví dụ đơn đã hủy thì không nên vẫn có nút “Thanh toán ngay”. Nếu trạng thái thay đổi trước khi người dùng mở email, trang đích cần đọc trạng thái hiện tại và giải thích tình hình, thay vì thực hiện hành động mù quáng.

## 17. Plain text và HTML phải cùng phản ánh một trạng thái

Với email nhiều định dạng, cả hai phiên bản cần được tạo từ cùng dữ liệu và cùng notification type:

~~~java
helper.setText(plainText, htmlText);
~~~

Ví dụ ORDER_SHIPPED:

Plain text:

~~~text
Đơn hàng ORD-2026-015 đã được gửi đi.
Mã theo dõi: VN123456
Theo dõi đơn hàng: https://example.com/tracking/VN123456
~~~

HTML:

~~~html
<h1>Đơn hàng đã được gửi đi</h1>
<p>Mã đơn hàng: <strong>ORD-2026-015</strong></p>
<p>Mã theo dõi: <strong>VN123456</strong></p>
<a href="https://example.com/tracking/VN123456">Theo dõi đơn hàng</a>
~~~

Không để HTML ghi SHIPPED nhưng plain text vẫn ghi PROCESSING. Cũng không để URL tracking trong HTML trỏ tới đơn khác với URL trong text.

Một renderer nhận **một notification model** rồi tạo cả hai chuỗi sẽ giúp giữ tính nhất quán. Nếu dùng template engine, nên render plain text và HTML từ cùng một model bất biến.

## 18. Nội dung đa ngôn ngữ theo locale

Người nhận có thể dùng ngôn ngữ khác nhau. Thay vì ghép chuỗi trực tiếp trong switch, có thể chọn template theo **locale**:

~~~text
ORDER_SHIPPED
  ├── vi-VN
  │    ├── subject
  │    ├── plain text
  │    └── HTML
  └── en-US
       ├── subject
       ├── plain text
       └── HTML
~~~

Ví dụ Java:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");

String subject = messageSource.getMessage(
        "mail.order.shipped.subject",
        new Object[] { orderCode },
        locale
);
~~~

MessageSource có thể quản lý các chuỗi như subject và nhãn dùng chung. Với body dài, template riêng theo locale thường dễ duy trì hơn một file properties chứa toàn bộ HTML.

### Lưu ý về locale

- Lấy locale từ hồ sơ người dùng hoặc tùy chọn đã xác thực.
- Có locale mặc định khi người dùng chưa chọn.
- Định dạng ngày, giờ, tiền tệ theo locale nhưng vẫn giữ múi giờ nghiệp vụ đúng.
- Không dịch mã trạng thái nội bộ; chỉ dịch nội dung hiển thị.
- Đảm bảo plain text và HTML cùng dùng một locale.
- Nếu thiếu template cho locale, có fallback được định nghĩa rõ ràng.

Không tự suy ra ngôn ngữ chỉ từ địa chỉ email hoặc quốc gia của domain.

## 19. Template theo trạng thái và khả năng bảo trì

Khi số trạng thái và loại email tăng, nên tách template theo event thay vì giữ một file khổng lồ với nhiều nhánh điều kiện.

Ví dụ cấu trúc:

~~~text
src/main/resources/mail/
  order/
    pending-payment.html
    pending-payment.txt
    paid.html
    paid.txt
    shipped.html
    shipped.txt
    delivered.html
    delivered.txt
    cancelled.html
    cancelled.txt
~~~

Một registry có thể ánh xạ event sang template:

~~~java
public record TemplatePair(
        String plainTextTemplate,
        String htmlTemplate
) {
}

public class OrderTemplateRegistry {

    public TemplatePair forEvent(OrderEventType eventType) {
        return switch (eventType) {
            case PAYMENT_REQUIRED -> new TemplatePair(
                    "mail/order/pending-payment.txt",
                    "mail/order/pending-payment.html"
            );
            case PAID -> new TemplatePair(
                    "mail/order/paid.txt",
                    "mail/order/paid.html"
            );
            case SHIPPED -> new TemplatePair(
                    "mail/order/shipped.txt",
                    "mail/order/shipped.html"
            );
            case DELIVERED -> new TemplatePair(
                    "mail/order/delivered.txt",
                    "mail/order/delivered.html"
            );
            case CANCELLED -> new TemplatePair(
                    "mail/order/cancelled.txt",
                    "mail/order/cancelled.html"
            );
        };
    }
}
~~~

OrderEventType là enum do ứng dụng định nghĩa. Ví dụ chỉ liệt kê một số event; cần bổ sung các loại còn lại nếu hệ thống hỗ trợ. Template registry chọn file, còn template renderer chịu trách nhiệm đọc và render dữ liệu.

### Không để template quyết định transition

Template có thể chọn cách trình bày event ORDER_SHIPPED, nhưng không nên tự quyết định rằng đơn hàng được phép chuyển từ CANCELLED sang SHIPPED. Quy tắc transition nằm trong domain/application service. Template chỉ trình bày một sự kiện đã hợp lệ.

## 20. Tránh gửi email cho những thay đổi không cần thông báo

Một đối tượng có thể có nhiều thay đổi nội bộ:

- Sửa ghi chú của nhân viên.
- Cập nhật timestamp đồng bộ.
- Gán lại nhân viên phụ trách.
- Cập nhật thông tin kỹ thuật của gateway.
- Sửa lỗi chính tả địa chỉ mà không đổi trạng thái.

Không phải thay đổi nào cũng cần email cho khách hàng. Nên xác định rõ **notification policy**:

| Loại thay đổi | Email khách hàng? | Lý do |
|---|---|---|
| Thanh toán thành công | Thường có | Sự kiện quan trọng |
| Đơn chuyển sang giao hàng | Thường có | Người nhận cần tracking |
| Ghi chú nội bộ thay đổi | Không | Không phải thông tin dành cho khách hàng |
| Cập nhật metadata kỹ thuật | Không | Không tạo giá trị cho người nhận |
| Thay đổi ngày giao dự kiến | Tùy chính sách | Có thể ảnh hưởng kế hoạch người mua |
| Hủy đơn | Thường có | Cần giải thích kết quả và bước tiếp theo |

Một notification policy giúp tránh spam và giữ email có ý nghĩa. Có thể gộp các thay đổi nhỏ thành một bản tóm tắt nếu nghiệp vụ cho phép.

## 21. Xử lý trạng thái đến sai thứ tự hoặc webhook lặp

Các hệ thống bên ngoài có thể gửi webhook nhiều lần hoặc không theo đúng thứ tự thời gian. Ví dụ:

1. Webhook payment.succeeded đến hai lần.
2. Webhook shipment.delivered đến trước một webhook shipment.in_transit bị trễ.
3. Một worker retry event cũ sau khi trạng thái đã đổi.

Nếu ứng dụng chỉ lấy payload rồi gửi email ngay, có thể gửi sai nội dung hoặc thông báo trùng.

### Xác thực event trước khi phát notification

- Xác minh chữ ký webhook hoặc cơ chế xác thực của nhà cung cấp.
- Dùng event ID để chống xử lý trùng.
- Kiểm tra version/timestamp và trạng thái hiện tại theo quy tắc nghiệp vụ.
- Áp dụng transition hợp lệ.
- Chỉ tạo notification khi event được chấp nhận.
- Lưu event gốc và kết quả xử lý để có thể điều tra.

Không dùng timestamp đơn lẻ làm bằng chứng tuyệt đối về thứ tự nếu nhà cung cấp có quy tắc version/sequence riêng. Cần dựa vào hợp đồng của nguồn event.

### Ví dụ xử lý idempotent ở mức ý tưởng

~~~java
@Transactional
public void handle(PaymentSucceededWebhook webhook) {
    if (processedEventRepository.existsByExternalId(webhook.eventId())) {
        return;
    }

    Order order = orderRepository.findById(webhook.orderId())
            .orElseThrow();

    order.markPaid(webhook.paymentReference());
    orderRepository.save(order);

    outboxRepository.save(
            NotificationOutbox.orderPaid(order, webhook.eventId())
    );

    processedEventRepository.save(
            ProcessedEvent.from(webhook.eventId())
    );
}
~~~

Đây là mã minh họa; cần có unique constraint cho external event ID và xử lý race condition trong database. Chỉ kiểm tra existsBy... rồi insert mà không có ràng buộc duy nhất vẫn có thể bị hai request đồng thời xử lý cùng event.

## 22. Bảo mật dữ liệu trong email theo trạng thái

Email thường rời khỏi hệ thống và có thể được chuyển tiếp hoặc lưu trong nhiều mailbox. Vì vậy, chỉ nên đưa thông tin cần thiết cho người nhận.

Ví dụ:

- Email PENDING_PAYMENT có thể chứa mã đơn và link thanh toán, nhưng không chứa thông tin thẻ.
- Email SHIPPED có thể chứa tracking number và link theo dõi, nhưng không tiết lộ ghi chú nội bộ.
- Email CANCELLED có thể giải thích lý do phù hợp, nhưng không gửi thông tin nhân viên hoặc dữ liệu điều tra nội bộ.
- Email REFUNDED có thể nêu số tiền và mã tham chiếu phù hợp, nhưng không hiển thị số tài khoản đầy đủ.

### URL và token

Nếu link cần token:

- Dùng HTTPS.
- Token có độ ngẫu nhiên đủ mạnh, thời hạn và phạm vi tác dụng rõ ràng.
- Không ghi token vào log.
- Không gửi token cho nhiều người nhận.
- Trang đích phải kiểm tra quyền và trạng thái hiện tại.
- Tránh hoàn tất thao tác nhạy cảm chỉ bằng GET vì email scanner có thể tự mở link.

### Escape nội dung HTML

Tên khách hàng, lý do hủy hoặc nội dung mô tả có thể chứa ký tự đặc biệt. Phải escape theo ngữ cảnh HTML text/attribute. Không nối trực tiếp dữ liệu người dùng vào markup hoặc href.

Với nội dung có thể chứa markup, cần chính sách sanitize cụ thể hoặc chỉ cho phép tập dữ liệu định dạng hạn chế. Template engine có escaping mặc định hữu ích nhưng phải tránh vô tình bật chế độ chèn HTML thô.

## 23. Kiểm soát recipient và consent

Trạng thái nghiệp vụ quyết định **loại thông báo**, nhưng recipient phải được xác định theo quyền và mục đích gửi:

- Email giao dịch có thể được gửi theo địa chỉ gắn với tài khoản hoặc đơn hàng, tùy quy định và consent áp dụng.
- Email nội bộ chỉ gửi tới nhóm/địa chỉ được phân quyền.
- Không lấy recipient tùy ý từ webhook chưa xác minh.
- Không đưa nhiều khách hàng không liên quan vào To/Cc nếu họ không được phép biết địa chỉ của nhau.
- Với thông báo marketing, cần tuân thủ consent, unsubscribe và chính sách pháp lý tương ứng.

Nếu một email giao dịch có người mua và người nhận hàng khác nhau, cần xác định rõ ai được nhận thông tin nào. Ví dụ người nhận hàng có thể cần lịch giao, nhưng không nhất thiết được nhận hóa đơn hoặc thông tin thanh toán.

## 24. Quan sát và truy vết notification

Khi email phụ thuộc trạng thái, cần truy vết được vì sao một email được tạo:

| Trường | Mục đích |
|---|---|
| eventId | Định danh sự kiện nguồn |
| aggregateId | Đơn hàng/tài khoản/đối tượng liên quan |
| previousStatus | Trạng thái trước transition |
| currentStatus | Trạng thái mới |
| notificationType | Loại email cần gửi |
| recipientRef | Tham chiếu recipient; hạn chế lưu email thô nếu không cần |
| templateKey | Template được chọn |
| locale | Ngôn ngữ render |
| attempt | Số lần gửi thử |
| providerMessageId | Định danh phía SMTP/ESP nếu có |
| status | PENDING, SENT_TO_PROVIDER, RETRY, FAILED hoặc UNKNOWN |

Log nên ghi event ID, notification ID, template key và loại lỗi đã được làm sạch. Không ghi toàn bộ body, mật khẩu SMTP, token hoặc attachment nhạy cảm.

### Phân biệt các mốc thành công

~~~text
Business transition committed
            |
            v
Notification created
            |
            v
Mail provider accepted
            |
            v
Provider / receiving server processing
            |
            v
Delivered / bounced / deferred (nếu có event)
            |
            v
Recipient opens or reads (không luôn quan sát được)
~~~

Không đặt trạng thái DELIVERED ngay khi JavaMailSender.send(...) trả về bình thường. Có thể dùng tên SENT_TO_PROVIDER hoặc SUBMITTED để phản ánh đúng kết quả mà ứng dụng biết được.

## 25. Kiểm thử mapping trạng thái và nội dung

Không cần kết nối SMTP thật để kiểm tra việc chọn nội dung. Có thể kiểm tra resolver bằng unit test:

~~~java
@Test
void shippedOrderUsesTrackingMessage() {
    OrderEmailData data = new OrderEmailData(
            "An",
            "ORD-2026-015",
            OrderStatus.SHIPPED,
            new BigDecimal("250000"),
            "VND",
            "VN123456",
            "https://example.com/tracking/VN123456",
            "https://example.com/orders/ORD-2026-015"
    );

    RenderedEmail email = resolver.resolve(data);

    assertTrue(email.subject().contains("đã được gửi đi"));
    assertTrue(email.plainText().contains("VN123456"));
    assertTrue(email.htmlText().contains("VN123456"));
}
~~~

Ví dụ dùng JUnit 5; resolver là implementation được inject hoặc khởi tạo trong test. Cần kiểm tra thêm trạng thái khác, locale, URL và dữ liệu biên.

### Kiểm tra service gửi mail bằng mock

Có thể mock JavaMailSender để xác nhận service tạo MimeMessage và gửi:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
MimeMessage message = new MimeMessage(Session.getInstance(new Properties()));
when(sender.createMimeMessage()).thenReturn(message);

MailNotificationService service = new MailNotificationService(sender);
service.send("customer@example.net", renderedEmail);

verify(sender).send(message);
~~~

Đây là ví dụ khái quát; test cần import Jakarta Mail Session, Properties, Mockito và có thể cần điều chỉnh cách so sánh đối tượng message theo setup. Mock xác nhận lời gọi ở tầng ứng dụng, **không chứng minh SMTP đã gửi hoặc email client render đúng**.

### Kiểm thử transition và notification riêng biệt

Nên có các nhóm kiểm thử:

1. **Domain test:** transition hợp lệ và không hợp lệ.
2. **Application test:** transition tạo đúng event/outbox record.
3. **Resolver test:** event/status chọn đúng subject và template.
4. **Renderer test:** plain text và HTML chứa cùng dữ liệu quan trọng.
5. **Mail service test:** tạo MIME và gọi JavaMailSender.
6. **Integration test:** dùng SMTP test server để quan sát MIME/transport.

Tách các lớp test giúp xác định lỗi nằm ở quy tắc nghiệp vụ, nội dung hay hạ tầng gửi.

## 26. Ví dụ end-to-end: xử lý sự kiện đơn hàng đã gửi đi

Một quy trình đơn giản có thể được chia như sau:

**Bước 1 — Application service xác nhận transition**

~~~java
@Transactional
public void shipOrder(String orderId, ShipmentInfo shipment) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    OrderStatus previous = order.getStatus();
    order.markShipped(shipment);
    orderRepository.save(order);

    outboxRepository.save(
            OrderNotificationOutbox.shipped(
                    order,
                    previous,
                    shipment
            )
    );
}
~~~

Order.markShipped(...) kiểm tra transition hợp lệ. OrderNotificationOutbox.shipped(...) tạo payload cần thiết trong cùng transaction. Đây là cấu trúc minh họa; kiểu entity và repository do ứng dụng định nghĩa.

**Bước 2 — Worker đọc outbox**

~~~java
public void process(OrderNotificationOutbox record) {
    if (record.isAlreadyProcessed()) {
        return;
    }

    OrderShippedEvent event = record.toEvent();
    RenderedEmail content = renderer.render(event);
    mailNotificationService.send(event.recipientEmail(), content);

    outboxRepository.markSubmitted(record.id());
}
~~~

Worker thực tế cần khóa/claim record để tránh hai worker gửi cùng lúc, lưu attempt và xử lý exception. Nếu gửi thành công nhưng cập nhật outbox thất bại, cần chính sách chống trùng hoặc đối soát.

**Bước 3 — Renderer tạo hai phiên bản**

~~~java
public RenderedEmail render(OrderShippedEvent event) {
    String subject = "Đơn hàng " + event.orderCode() + " đã được gửi đi";

    String plain = """
            Đơn hàng %s đã được gửi đi.
            Mã theo dõi: %s
            Theo dõi: %s
            """.formatted(
            event.orderCode(),
            event.trackingNumber(),
            event.trackingUrl()
    );

    String html = shippedTemplate.render(event);

    return new RenderedEmail(subject, plain, html);
}
~~~

shippedTemplate là template renderer của ứng dụng; khi render HTML phải escape text và kiểm tra URL. Plain text và HTML dùng cùng event snapshot.

**Bước 4 — Mail service gửi**

Mail service gọi:

~~~java
helper.setText(content.plainText(), content.htmlText());
mailSender.send(message);
~~~

Tầng gửi không cần tự suy đoán trạng thái đơn hàng. Nó nhận nội dung đã được chọn và chịu trách nhiệm tạo MIME cùng việc nộp thư.

## 27. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
|---|---|---|
| Gửi email trong setter/entity | Domain phụ thuộc SMTP, side effect khó kiểm soát | Phát event hoặc tạo outbox từ application service |
| Gửi mỗi lần entity save | Email trùng khi metadata thay đổi | Gửi theo transition/event có ý nghĩa |
| Dựa vào current state khi worker chạy | Nội dung có thể không khớp event cũ | Dùng event snapshot/version phù hợp |
| Một template chung cho mọi trạng thái | Người nhận không biết điều gì xảy ra | Mapping event/status sang template rõ ràng |
| Một switch khổng lồ chứa mọi HTML | Khó bảo trì và kiểm thử | Tách resolver, renderer và template |
| Plain text và HTML lấy dữ liệu riêng | Hai bản có thể mâu thuẫn | Render từ cùng model bất biến |
| Gửi trước khi transaction commit | Email có thể báo thay đổi đã rollback | AFTER_COMMIT hoặc outbox |
| Chỉ dùng in-memory event cho thông báo quan trọng | Event có thể mất khi process dừng | Transactional outbox |
| Retry mù khi timeout | Có thể gửi trùng | Event ID, attempt tracking và đối soát |
| Gửi cùng nội dung cho mọi audience | Lộ dữ liệu nội bộ | Tách template và recipient policy theo audience |
| Dùng URL từ payload chưa xác minh | Open redirect/phishing hoặc SSRF ở luồng tải tài nguyên | Tạo URL từ domain được phép và xác thực event |
| Đánh dấu DELIVERED ngay sau send | Báo cáo sai trạng thái chuyển phát | Dùng SENT_TO_PROVIDER và xử lý bounce event |
| Gửi mọi thay đổi kỹ thuật | Làm phiền người nhận | Notification policy lọc sự kiện có ý nghĩa |

## 28. Quy trình thiết kế notification theo trạng thái

Một quy trình có thể áp dụng cho nhiều loại đối tượng nghiệp vụ:

1. **Liệt kê trạng thái và transition hợp lệ** của đối tượng.
2. **Xác định event** phát sinh khi transition được chấp nhận.
3. **Quyết định audience và recipient** cho từng event.
4. **Chọn nội dung cần thông báo**: subject, plain text, HTML, link và attachment nếu có.
5. **Tạo template theo event/locale/audience** khi số lượng nội dung tăng.
6. **Lưu snapshot hoặc payload** để nội dung không bị sai lệch nếu gửi trễ.
7. **Ghi notification/outbox** cùng transaction khi yêu cầu độ tin cậy cao.
8. **Render và gửi qua JavaMailSender** ở worker hoặc listener thích hợp.
9. **Ghi attempt và kết quả**; retry có giới hạn và chống trùng.
10. **Kiểm tra trải nghiệm** ở email client, đồng thời giữ bản text đầy đủ.

Không phải mọi ứng dụng cần outbox hoặc template engine ngay từ đầu. Với một hệ thống nhỏ, application service + resolver + mail service có thể đủ. Khi yêu cầu về độ tin cậy, số lượng trạng thái và khối lượng gửi tăng, có thể bổ sung queue, outbox và hệ thống template chuyên biệt.

## 29. Ghi nhớ

Nội dung email thay đổi theo trạng thái nghiệp vụ khi ứng dụng ánh xạ **transition hoặc business event** sang thông báo phù hợp. Trạng thái hiện tại cho biết đối tượng đang ở đâu; event cho biết điều gì vừa xảy ra. Chỉ gửi email khi có một sự kiện có ý nghĩa với người nhận, không gửi chỉ vì entity được lưu.

Trong Spring Framework Mail, nên tách quy tắc nghiệp vụ, lựa chọn template, render nội dung và gửi thư thành các trách nhiệm riêng. **JavaMailSender** và **MimeMessageHelper** tạo thông điệp; setText(plainText, htmlText) cung cấp hai phiên bản nội dung. Plain text và HTML cần dùng cùng dữ liệu, recipient và hành động phù hợp với event.

Với thông báo quan trọng, lưu ý thời điểm transaction commit, transactional outbox, event identity, idempotency, retry và trạng thái chưa rõ. Kiểm soát recipient, locale, URL, token và dữ liệu nhạy cảm trước khi gửi. **Email tốt phải phản ánh đúng điều vừa xảy ra, nói đúng với người nhận và đưa ra bước tiếp theo còn hợp lệ.**
