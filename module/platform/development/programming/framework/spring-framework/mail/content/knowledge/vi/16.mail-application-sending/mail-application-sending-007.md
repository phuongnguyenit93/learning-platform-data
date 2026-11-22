# Xử lý email bắt buộc và email tùy chọn trong Spring Framework Mail

Không phải email nào ứng dụng gửi cũng có cùng mức độ quan trọng. Email đặt lại mật khẩu, mã xác thực hoặc cảnh báo bảo mật có thể là một phần thiết yếu của quy trình người dùng. Email xác nhận đơn hàng có thể là nghĩa vụ thông báo mà hệ thống phải tiếp tục thực hiện ngay cả khi giao dịch mua hàng đã hoàn tất. Trong khi đó, bản tin, khuyến mại hoặc gợi ý sản phẩm thường là nội dung tùy chọn: người dùng có thể từ chối nhận và lỗi gửi không được làm gián đoạn chức năng chính.

Trong Spring Framework Mail, cả hai nhóm đều có thể được gửi qua JavaMailSender. Điểm khác nhau nằm ở **chính sách nghiệp vụ quanh việc gửi**: lúc nào được phép gửi, có cần sự đồng ý hay không, lỗi gửi ảnh hưởng thế nào đến thao tác chính, có phải retry, lưu trạng thái ra sao và khi nào được phép bỏ qua.

Một thiết kế tốt cần phân biệt ba khái niệm:

- **Email bắt buộc:** thông điệp mà nghiệp vụ hoặc chính sách sản phẩm yêu cầu phải được xử lý. Không được âm thầm bỏ mất thông điệp này.
- **Email tùy chọn:** thông điệp có thể gửi khi người nhận đủ điều kiện và cho phép; việc không gửi thường không ảnh hưởng giao dịch chính.
- **Cách giao email:** đồng bộ để người dùng nhận kết quả ngay, hoặc bất đồng bộ qua hàng đợi/outbox để có thể retry và theo dõi.

Email bắt buộc không đồng nghĩa mọi giao dịch phải chờ SMTP hoàn tất. Email tùy chọn cũng không có nghĩa có thể gửi bất chấp lỗi hoặc sở thích của người nhận. **Chính sách nghiệp vụ quyết định mức độ bắt buộc; kiến trúc gửi quyết định cách thực hiện chính sách đó đáng tin cậy.**

## 1. Phân biệt email bắt buộc và email tùy chọn

### Email bắt buộc

Email bắt buộc thường phục vụ bảo mật, xác thực, trạng thái giao dịch hoặc thông báo mà sản phẩm cam kết với người dùng. Ví dụ:

- Mã xác thực hoặc liên kết xác minh địa chỉ email.
- Liên kết đặt lại mật khẩu do người dùng yêu cầu.
- Cảnh báo đăng nhập hoặc thay đổi thông tin bảo mật.
- Xác nhận giao dịch, biên nhận hoặc hóa đơn theo quy trình sản phẩm.
- Thông báo thay đổi trạng thái đơn hàng mà khách hàng cần biết để tiếp tục thao tác.
- Thông báo vận hành quan trọng mà chính sách tổ chức yêu cầu gửi.

Với nhóm này, ứng dụng cần ghi nhận việc gửi, xử lý lỗi có chủ đích và không âm thầm đánh dấu hoàn tất nếu thông điệp chưa được xử lý theo chính sách.

Tuy nhiên, không phải mọi email giao dịch đều cần chặn giao dịch chính khi SMTP lỗi. Ví dụ, sau khi đơn hàng đã được ghi nhận thành công, việc email xác nhận tạm thời chưa gửi được thường không nên làm đơn hàng bị rollback. Thay vào đó, hệ thống lưu yêu cầu gửi và retry. Ngược lại, nếu email là kênh duy nhất để người dùng nhận mã xác thực trước khi đăng nhập, việc không gửi được mã có thể khiến bước xác thực chưa thể hoàn tất.

### Email tùy chọn

Email tùy chọn thường phục vụ tương tác, nội dung bổ sung hoặc marketing. Ví dụ:

- Bản tin định kỳ.
- Thông báo khuyến mại, giảm giá hoặc chiến dịch.
- Gợi ý sản phẩm hoặc nội dung cá nhân hóa.
- Lời mời tham gia khảo sát, webinar hoặc sự kiện.
- Nhắc nhở không thiết yếu mà người dùng có thể tắt.
- Email chăm sóc hoặc giới thiệu tính năng mới.

Nhóm này thường phụ thuộc vào tùy chọn nhận email, sự đồng ý hoặc cơ sở xử lý phù hợp với chính sách sản phẩm và quy định áp dụng. Nếu người dùng đã từ chối nhận, hệ thống phải bỏ qua hoặc đánh dấu suppressed. Nếu SMTP lỗi, thao tác mua hàng, đăng nhập hoặc cập nhật hồ sơ không nên thất bại chỉ vì một email marketing không gửi được.

### Bảng so sánh

| Tiêu chí | Email bắt buộc | Email tùy chọn |
| --- | --- | --- |
| Mục tiêu | Bảo mật, xác thực, giao dịch hoặc nghĩa vụ thông báo | Tương tác, nội dung bổ sung, marketing |
| Điều kiện gửi | Theo sự kiện và chính sách nghiệp vụ | Theo sự kiện, preference, consent và giới hạn gửi |
| Người dùng có thể tắt? | Tùy loại thông điệp và chính sách áp dụng; không nên gộp chung với marketing | Thường có tùy chọn tắt hoặc unsubscribe |
| Khi SMTP lỗi | Ghi nhận, retry hoặc chặn bước thực sự phụ thuộc email | Không chặn thao tác chính; có thể retry giới hạn hoặc bỏ qua |
| Mất thông điệp có chấp nhận được không? | Thường không; cần theo dõi đến trạng thái cuối | Có thể chấp nhận theo policy |
| Retry | Có chính sách rõ, thường bền vững cho thông báo giao dịch | Có giới hạn, có thể hết hạn hoặc bị hủy |
| Audit | Thường cần lưu dấu vết xử lý và kết quả | Cần ghi nhận consent, suppression và kết quả theo nhu cầu |
| Ví dụ | OTP, reset password, xác nhận đơn hàng | Newsletter, ưu đãi, gợi ý sản phẩm |

### Không phân loại chỉ theo tên email

Một thông báo có tiêu đề “Thông báo tài khoản” chưa chắc là bắt buộc. Một email “Cập nhật đơn hàng” có thể là thông báo thiết yếu hoặc chỉ là lời nhắc tiện ích tùy quy trình. Hãy xem:

1. Nếu không gửi, người dùng có mất khả năng hoàn tất một bước quan trọng không?
2. Hệ thống có cam kết gửi thông điệp đó không?
3. Thông điệp có chứa nội dung quảng cáo hoặc gợi ý thương mại không?
4. Người dùng có quyền từ chối theo chính sách sản phẩm không?
5. Có kênh thay thế đáng tin cậy không?
6. Khi gửi thất bại, nghiệp vụ cần chờ, retry hay tiếp tục?

Nếu một email giao dịch chứa thêm nội dung khuyến mại, cần phân loại phần nội dung đó cẩn thận. Có thể tách thông báo giao dịch khỏi chiến dịch marketing để tránh việc nội dung tùy chọn làm thay đổi cách xử lý toàn bộ email.

**Phân loại nghiệp vụ không phải tư vấn pháp lý.** Nghĩa vụ gửi, consent và quyền unsubscribe phụ thuộc loại thông điệp, nơi hoạt động và quy định áp dụng. Hãy để chính sách sản phẩm/pháp chế xác định nhóm nào thực sự bắt buộc.

## 2. Tách chính sách gửi khỏi nội dung email

Không nên để service quyết định chính sách bằng các điều kiện rải rác như:

~~~java
if (isMarketing) {
    // Có thể bỏ qua lỗi
} else {
    // Ném lỗi
}
~~~

Cách này nhanh chóng trở nên khó hiểu khi ứng dụng có thêm nhiều loại thông báo. Một thiết kế rõ ràng tách:

- **Notification type:** loại thông điệp, ví dụ PASSWORD_RESET hoặc ORDER_CONFIRMED.
- **Requirement:** bắt buộc hay tùy chọn theo nghiệp vụ.
- **Delivery policy:** đồng bộ, bền vững bất đồng bộ hay best-effort.
- **Recipient preference:** người nhận có cho phép loại email tùy chọn này không.
- **Template:** nội dung HTML/text được render.
- **Transport:** JavaMailSender hoặc dịch vụ email bên ngoài.

Ví dụ enum:

~~~java
public enum MailCategory {
    SECURITY_REQUIRED,
    TRANSACTIONAL_REQUIRED,
    PRODUCT_UPDATE_OPTIONAL,
    MARKETING_OPTIONAL
}

public enum DeliveryMode {
    BLOCKING,
    DURABLE_ASYNC,
    BEST_EFFORT
}
~~~

Hai enum phục vụ hai câu hỏi khác nhau. MailCategory biểu diễn chính sách nghiệp vụ; DeliveryMode biểu diễn cách giao. Ví dụ:

| MailCategory | DeliveryMode có thể dùng |
| --- | --- |
| SECURITY_REQUIRED | BLOCKING cho mã xác thực cần gửi ngay; hoặc DURABLE_ASYNC cho cảnh báo bảo mật |
| TRANSACTIONAL_REQUIRED | Thường DURABLE_ASYNC sau khi giao dịch được commit |
| PRODUCT_UPDATE_OPTIONAL | BEST_EFFORT hoặc DURABLE_ASYNC có thời hạn |
| MARKETING_OPTIONAL | BEST_EFFORT hoặc queue có giới hạn và kiểm tra consent trước khi gửi |

Không nên suy ra DeliveryMode chỉ từ Category. Một thông báo bắt buộc có thể cần được lưu bền vững và gửi nền; một thông báo tùy chọn có thể cần queue để kiểm soát tần suất.

## 3. Chính sách email tùy chọn và lựa chọn của người nhận

Với email tùy chọn, cần kiểm tra preference trước khi tạo yêu cầu gửi. Ví dụ người dùng có thể bật nhận bản tin nhưng tắt khuyến mại:

~~~java
public record EmailPreferences(
        boolean productUpdates,
        boolean marketing,
        boolean newsletters
) {
}
~~~

Một policy service có thể kiểm tra:

~~~java
public boolean maySendOptional(
        MailCategory category,
        EmailPreferences preferences) {

    return switch (category) {
        case PRODUCT_UPDATE_OPTIONAL -> preferences.productUpdates();
        case MARKETING_OPTIONAL -> preferences.marketing();
        default -> true;
    };
}
~~~

Đây là ví dụ tối giản. Trong hệ thống thật, preference có thể cần trạng thái consent, thời điểm, nguồn thu thập, phiên bản điều khoản, tenant, loại chiến dịch, suppression list và trạng thái địa chỉ email.

### Kiểm tra preference ở hai thời điểm

Đối với email được xếp hàng rồi gửi sau, nên kiểm tra preference:

1. **Khi tạo yêu cầu:** không đưa email tùy chọn vào queue nếu người nhận đã tắt loại đó.
2. **Ngay trước khi gửi:** người nhận có thể thay đổi lựa chọn trong lúc email đang chờ.

~~~text
User enables newsletter
       |
       v
Campaign creates optional notification
       |
       v
Notification waits in queue
       |
       +---- User unsubscribes
       |
       v
Mail worker checks current preference
       |
       v
SUPPRESSED (do not send)
~~~

Nếu chỉ kiểm tra lúc enqueue, một email đã nằm trong queue có thể được gửi sau khi người dùng unsubscribe. Kiểm tra lại ngay trước khi submit giúp giảm tình huống này.

### Unsubscribe và suppression

Với chiến dịch marketing, hệ thống nên có cơ chế unsubscribe dễ sử dụng và suppression list. Khi người nhận từ chối:

- Ghi nhận thời điểm và phạm vi unsubscribe.
- Ngừng tạo các email thuộc nhóm tương ứng.
- Hủy hoặc suppress các job chưa gửi nếu policy yêu cầu.
- Kiểm tra lại preference trước khi gửi job đã chờ.
- Không xóa dấu vết suppression chỉ vì một chiến dịch mới được tạo.

Nếu một địa chỉ bị bounce vĩnh viễn hoặc bị báo spam, hệ thống có thể đưa vào suppression list để tránh tiếp tục gửi. Quy tắc suppression và quyền gửi thông báo giao dịch phải được tách theo chính sách; không dùng một boolean “email enabled” cho tất cả các loại.

### Không trộn quảng cáo vào email bắt buộc

Một email reset password nên tập trung vào việc reset password. Nếu thêm nhiều ưu đãi, nội dung giao dịch có thể trở nên khó phân loại và làm người nhận khó nhận ra hành động bảo mật cần thiết.

Nên tách:

- Email giao dịch/bảo mật chỉ chứa thông tin cần thiết cho sự kiện.
- Email marketing riêng, có kiểm tra consent/preferences.

Nếu có nội dung quảng bá trong email giao dịch, cần xem lại phân loại và chính sách gửi trước khi triển khai.

## 4. Quyết định lỗi gửi có chặn thao tác chính hay không

Đây là quyết định quan trọng nhất khi xử lý email bắt buộc và tùy chọn. Hãy hỏi: **email có phải điều kiện để hoàn tất chính thao tác đang thực hiện không?**

### Trường hợp cần chặn

Ví dụ người dùng yêu cầu mã OTP qua email để xác minh. Nếu hệ thống không thể gửi mã, người dùng chưa thể hoàn tất xác minh qua kênh đó. Ứng dụng cần trả kết quả phù hợp như “không thể gửi mã lúc này”, cho phép thử lại có giới hạn hoặc cung cấp kênh hỗ trợ thay thế.

Trong trường hợp này:

- Không đánh dấu xác minh thành công.
- Không trả mã bí mật trong response hoặc log.
- Không tạo vô hạn mã mới khi retry.
- Không cho phép dùng token hết hạn hoặc token đã bị thu hồi.
- Theo dõi lỗi gửi để người dùng có thể thử lại theo policy.

### Trường hợp không nên chặn

Ví dụ đơn hàng đã được tạo và thanh toán thành công, email biên nhận bị SMTP từ chối tạm thời. Nếu rollback đơn hàng chỉ vì email không gửi được, hệ thống có thể tạo trạng thái giao dịch sai hoặc gây hoàn tiền ngoài ý muốn.

Thay vào đó:

- Commit đơn hàng và một bản ghi yêu cầu gửi email trong cùng transaction.
- Worker gửi email sau commit.
- Nếu gửi lỗi tạm thời, retry.
- Nếu lỗi vĩnh viễn, ghi trạng thái cần xử lý và thông báo qua kênh vận hành phù hợp.

Email vẫn là thông điệp bắt buộc cần được xử lý, nhưng việc submit SMTP không nằm trong transaction tạo đơn hàng.

### Ma trận quyết định

| Tình huống | SMTP lỗi thì thao tác chính? | Cách xử lý |
| --- | --- | --- |
| Gửi OTP trước khi xác minh | Chưa hoàn tất bước xác minh | Báo không gửi được, retry/kênh thay thế |
| Gửi link reset password | Không xác nhận reset đã hoàn tất | Giữ yêu cầu hợp lệ trong thời hạn, retry theo policy |
| Gửi biên nhận sau thanh toán | Giao dịch vẫn thành công | Outbox và retry, không rollback thanh toán |
| Gửi xác nhận đơn hàng | Đơn hàng vẫn được ghi nhận | Outbox, retry và theo dõi |
| Gửi newsletter | Không ảnh hưởng chức năng chính | Kiểm tra consent; bỏ qua/suppress hoặc retry giới hạn |
| Gửi khuyến mại sau đăng ký | Không ảnh hưởng đăng ký | Best-effort; không làm đăng ký thất bại |

**“Bắt buộc” nói về trách nhiệm xử lý thông điệp, không tự động nói rằng HTTP request phải chờ SMTP.**

## 5. Gửi đồng bộ và gửi bất đồng bộ

Spring cung cấp JavaMailSender để gửi email. Một lời gọi đơn giản:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setTo("user@example.com");
message.setSubject("Thông báo");
message.setText("Nội dung email");

mailSender.send(message);
~~~

Lệnh send thường gọi SMTP transport trong luồng đang thực thi. Nếu SMTP chậm hoặc không khả dụng, request có thể phải chờ và nhận exception.

### Gửi đồng bộ (blocking)

Ưu điểm:

- Có kết quả submit ngay trong luồng hiện tại.
- Dễ phản hồi cho người dùng khi email là bước thiết yếu.
- Luồng code đơn giản với trường hợp nhỏ.

Nhược điểm:

- Request phụ thuộc độ trễ và khả năng sẵn sàng của SMTP.
- SMTP timeout làm tăng thời gian phản hồi.
- Nếu gọi trong transaction database, transaction có thể bị giữ mở trong lúc chờ mạng.
- Không tự bảo đảm email đã đến mailbox hoặc được người nhận đọc.
- Khó retry bền vững nếu process dừng giữa chừng.

Chỉ nên dùng đồng bộ khi kết quả gửi thực sự cần thiết cho phản hồi tức thời và thời gian chờ được kiểm soát. Không nên giữ transaction database mở trong lúc gọi SMTP.

### Gửi bất đồng bộ (asynchronous)

Luồng bất đồng bộ lưu yêu cầu gửi trước, sau đó worker thực hiện:

~~~text
HTTP request / business command
          |
          v
Business transaction
  - update domain data
  - insert email outbox record
          |
          v
        COMMIT
          |
          v
      Mail worker
          |
          v
     Render template
          |
          v
    JavaMailSender.send
          |
          v
   Update delivery state
~~~

Ưu điểm:

- Không giữ request chờ SMTP.
- Có thể retry khi SMTP lỗi tạm thời.
- Có trạng thái để quan sát và vận hành.
- Có thể giới hạn tốc độ gửi và tách worker khỏi web application.
- Không làm mất yêu cầu gửi nếu domain transaction và outbox được commit cùng nhau.

Nhược điểm:

- Email không được submit ngay lập tức.
- Cần quản lý queue/outbox, worker, retry và trạng thái.
- Cần xử lý duplicate do worker retry hoặc process dừng giữa chừng.
- Cần quyết định template version và dữ liệu nào được giữ đến lúc gửi.

Với email giao dịch bắt buộc, asynchronous outbox thường phù hợp hơn vì bảo đảm yêu cầu gửi được lưu bền vững mà không làm transaction nghiệp vụ phụ thuộc SMTP.

## 6. Vì sao không gửi SMTP bên trong transaction database?

Ví dụ không nên:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    mailSender.send(buildConfirmation(order));

    return order;
}
~~~

Nếu SMTP mất 8 giây, transaction database có thể bị giữ mở trong khoảng thời gian đó. Nếu SMTP thành công nhưng transaction database rollback, người nhận có thể nhận email xác nhận cho đơn hàng không tồn tại. Ngược lại, database commit thành công nhưng process dừng trước khi gửi email thì thông điệp bị mất.

Hai hệ thống (database và SMTP) không cùng tham gia một transaction ACID. Không thể giả định rollback database sẽ thu hồi email đã được SMTP relay chấp nhận.

### Gửi sau khi transaction commit

Với trường hợp đơn giản, Spring hỗ trợ Transaction-bound event:

~~~java
public record OrderPlacedEvent(
        String orderId,
        String recipientEmail
) {
}
~~~

Phát event trong transaction:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    publisher.publishEvent(new OrderPlacedEvent(
            order.getId(),
            order.getCustomerEmail()));

    return order;
}
~~~

Lắng nghe sau commit:

~~~java
@Component
public class OrderMailListener {

    private final OrderMailService mailService;

    public OrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlacedEvent event) {
        mailService.sendOrderConfirmation(event);
    }
}
~~~

Event listener này tránh gửi email trước khi transaction commit. Tuy nhiên, **transactional event trong bộ nhớ không phải durable queue**. Nếu process dừng sau commit nhưng trước khi listener xử lý, event có thể bị mất. Nếu listener gửi lỗi, việc retry cũng cần được thiết kế riêng.

Có thể dùng @Async cùng event listener để chạy ở thread khác, nhưng @Async chỉ thay đổi cách thực thi; nó không tự tạo lưu trữ bền vững. Với thông báo bắt buộc cần bảo đảm không bị mất, hãy cân nhắc transactional outbox.

## 7. Transactional outbox cho email bắt buộc

Transactional outbox lưu yêu cầu gửi email trong cùng transaction với dữ liệu nghiệp vụ. Database bảo đảm cả hai cùng commit hoặc cùng rollback.

Ví dụ:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    EmailOutboxMessage outbox = EmailOutboxMessage.pending(
            UUID.randomUUID(),
            "ORDER_CONFIRMED",
            order.getCustomerEmail(),
            order.getId());

    outboxRepository.save(outbox);
    return order;
}
~~~

Nếu transaction commit, cả đơn hàng và email outbox record cùng tồn tại. Nếu rollback, cả hai đều không tồn tại. Worker có thể đọc outbox record sau đó.

### Một mô hình outbox đơn giản

~~~java
public enum OutboxStatus {
    PENDING,
    PROCESSING,
    SUBMITTED,
    RETRY_PENDING,
    FAILED,
    SUPPRESSED
}

public record EmailOutboxMessage(
        UUID id,
        String notificationType,
        String recipient,
        String aggregateId,
        String templateVersion,
        OutboxStatus status,
        int attempts,
        Instant nextAttemptAt
) {
}
~~~

Đây là record minh họa; entity persistence thật cần thêm cột thời điểm tạo/cập nhật, lease/lock, lỗi gần nhất đã được làm sạch, correlation ID và các trường theo nhu cầu.

### Các cột thường cần

| Trường | Mục đích |
| --- | --- |
| id | ID duy nhất của notification/outbox event |
| notification_type | Loại email, không dùng subject để suy luận policy |
| recipient | Người nhận đã được xác định theo nghiệp vụ |
| aggregate_id | ID đơn hàng/tài khoản/giao dịch liên quan |
| payload | Dữ liệu tối thiểu cần để render |
| template_version | Phiên bản template được chọn nếu cần tái lập nội dung |
| status | Trạng thái xử lý |
| attempts | Số lần đã thử |
| next_attempt_at | Thời điểm được phép thử lại |
| locked_until / lease_owner | Tránh nhiều worker xử lý cùng record đồng thời |
| last_error_code | Mã lỗi đã chuẩn hóa, không lưu bí mật |
| created_at / updated_at | Audit và vận hành |

Không nhất thiết lưu toàn bộ HTML đã render trong outbox. Có thể lưu event payload và render khi worker chạy. Nếu nội dung cần bất biến để kiểm toán, có thể lưu template version hoặc snapshot đã render theo chính sách bảo vệ dữ liệu và retention.

### Worker xử lý outbox

~~~java
@Component
public class EmailOutboxWorker {

    private final EmailOutboxRepository repository;
    private final MailDispatcher dispatcher;

    public EmailOutboxWorker(
            EmailOutboxRepository repository,
            MailDispatcher dispatcher) {
        this.repository = repository;
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelay = 1000)
    public void dispatchPending() {
        List<EmailOutboxMessage> messages =
                repository.claimDueMessages(50);

        for (EmailOutboxMessage message : messages) {
            dispatcher.dispatch(message);
        }
    }
}
~~~

Phương thức claimDueMessages cần được triển khai bằng transaction/locking phù hợp với database để chỉ một worker sở hữu một record trong thời gian lease. Không nên chỉ SELECT PENDING rồi UPDATE sau mà không có cơ chế claim nguyên tử; nhiều instance có thể gửi cùng một email.

### Cập nhật trạng thái sau khi gửi

~~~text
PENDING
  |
  v
PROCESSING
  |
  +-- SMTP accepted --> SUBMITTED
  |
  +-- Temporary error --> RETRY_PENDING
  |
  +-- Permanent error --> FAILED
  |
  +-- Optional + preference disabled --> SUPPRESSED
~~~

SUBMITTED chỉ có nghĩa SMTP relay đã chấp nhận thông điệp theo kết quả mà ứng dụng nhận được. Nó không đồng nghĩa người nhận đã nhận trong inbox, mở hoặc đọc thư.

## 8. Xử lý email tùy chọn mà không làm gián đoạn nghiệp vụ

Với newsletter hoặc khuyến mại, service chính không nên trực tiếp chờ JavaMailSender:

~~~java
@Transactional
public void completeRegistration(RegistrationCommand command) {
    User user = userRepository.save(createUser(command));

    // Đăng ký đã hoàn tất; email marketing là tùy chọn.
    optionalMailService.enqueueWelcomeCampaign(user.getId());
}
~~~

Đoạn code trên chỉ minh họa ý tưởng. Nếu enqueue dùng database, nên ghi outbox cùng transaction; nếu gọi một queue ngoài database, cần xem xét tính nhất quán giữa commit và publish.

Khi worker xử lý:

1. Tải recipient và preference hiện tại.
2. Xác nhận email thuộc đúng user/tenant.
3. Kiểm tra consent cho đúng category.
4. Kiểm tra suppression, unsubscribe và bounce.
5. Kiểm tra frequency cap và campaign expiry.
6. Render template.
7. Submit email.
8. Ghi kết quả hoặc suppress.

Nếu preference đã tắt, cập nhật trạng thái SUPPRESSED và không gọi SMTP. Đây không phải lỗi gửi; đó là quyết định đúng theo policy.

### Email tùy chọn có thể hết hạn

Một ưu đãi chỉ có hiệu lực đến một ngày cụ thể không nên được retry vô hạn sau khi chiến dịch kết thúc. Có thể lưu expires_at, campaign_id, category, consent version, frequency bucket và suppression reason. Khi worker nhận job quá hạn, đánh dấu EXPIRED hoặc SUPPRESSED. Không gửi một khuyến mại đã hết hạn chỉ vì queue bị tồn đọng.

## 9. Xây dựng mail policy rõ ràng

Một service policy có thể trả về quyết định trước khi enqueue hoặc dispatch:

~~~java
public enum MailDecision {
    ALLOW,
    SUPPRESS,
    REQUIRE_BLOCKING_DELIVERY,
    REQUIRE_DURABLE_DELIVERY
}

public class MailPolicy {

    public MailDecision decide(
            MailCategory category,
            EmailPreferences preferences) {

        return switch (category) {
            case SECURITY_REQUIRED ->
                    MailDecision.REQUIRE_BLOCKING_DELIVERY;
            case TRANSACTIONAL_REQUIRED ->
                    MailDecision.REQUIRE_DURABLE_DELIVERY;
            case PRODUCT_UPDATE_OPTIONAL ->
                    preferences.productUpdates()
                            ? MailDecision.ALLOW
                            : MailDecision.SUPPRESS;
            case MARKETING_OPTIONAL ->
                    preferences.marketing()
                            ? MailDecision.ALLOW
                            : MailDecision.SUPPRESS;
        };
    }
}
~~~

Ví dụ này thể hiện một policy cụ thể: thông báo bảo mật dùng luồng cần kết quả ngay, email giao dịch dùng outbox, còn marketing phụ thuộc preference. Trong sản phẩm thật, có thể có nhiều policy theo notification type, mức độ khẩn cấp, kênh thay thế, locale và jurisdiction.

### Không để boolean mơ hồ điều khiển chính sách

Một API như:

~~~java
sendEmail(message, true);
~~~

không nói rõ true có nghĩa là bắt buộc, gửi đồng bộ, retry hay bỏ qua lỗi. Dùng enum hoặc object policy có tên rõ:

~~~java
sendEmail(message, DeliveryMode.DURABLE_ASYNC);
~~~

Hoặc một command có cả category và policy. Tên rõ giúp code review và vận hành dễ hiểu hơn.

## 10. Gửi nội dung text hoặc HTML theo chính sách

Sau khi policy cho phép gửi và nội dung đã được render, Spring Mail hỗ trợ SimpleMailMessage cho email text đơn giản và MimeMessageHelper cho MIME/HTML/attachment.

### Email text đơn giản

~~~java
public void sendPlainText(
        String recipient,
        String subject,
        String body) {

    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("notifications@example.com");
    message.setTo(recipient);
    message.setSubject(subject);
    message.setText(body);

    mailSender.send(message);
}
~~~

### Email HTML và plain text alternative

~~~java
public void sendHtml(
        String recipient,
        String subject,
        String plainText,
        String htmlText) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8");

    helper.setFrom("notifications@example.com");
    helper.setTo(recipient);
    helper.setSubject(subject);
    helper.setText(plainText, htmlText);

    mailSender.send(message);
}
~~~

Các method trên chỉ đảm nhiệm việc tạo và submit message. Việc quyết định category, consent, retry, outbox và failure policy nên được xử lý ở lớp điều phối trước đó.

### Không đặt chính sách vào template

Template chỉ nên quyết định cách trình bày. Không nên nhúng logic như “nếu người dùng unsubscribe thì ẩn footer” rồi vẫn gửi email marketing. Quyền gửi phải được kiểm tra ở policy/service layer trước khi render và trước khi submit.

## 11. Xử lý lỗi Spring Mail

JavaMailSender có thể ném các exception thuộc hệ thống Spring Mail khi tạo hoặc gửi message. Phần lớn lỗi transport được biểu diễn qua MailException hoặc các subclass. Tuy nhiên, không phải mọi exception đều có cùng khả năng retry.

### Phân loại lỗi

| Nhóm | Ví dụ | Retry? |
| --- | --- | --- |
| Lỗi cấu hình | SMTP host/port sai, thiếu bean | Không retry mù; sửa cấu hình |
| Authentication | Username/password hoặc quyền SMTP sai | Không retry liên tục; cần sửa credential/quyền |
| Lỗi kết nối tạm thời | Connection timeout, server tạm unavailable | Có thể retry với backoff |
| Server tạm từ chối | SMTP 4xx | Thường có thể retry theo policy |
| Recipient không hợp lệ | Địa chỉ sai hoặc mailbox bị từ chối vĩnh viễn | Không retry vô hạn |
| Sender/policy bị từ chối | MAIL FROM hoặc relay policy không cho phép | Cần sửa cấu hình/chính sách |
| Lỗi tạo MIME | Attachment/resource lỗi, nội dung không hợp lệ | Thường không retry cho đến khi sửa dữ liệu |
| Lỗi render template | Template thiếu hoặc sai cú pháp | Không retry mù; cần sửa template/config |

Spring Mail exception có thể bọc exception từ Jakarta Mail. Nếu cần phân loại theo SMTP response code, nên chuẩn hóa tại một adapter transport và kiểm tra cause/response theo thư viện đang dùng. Không nên parse chuỗi exception message bằng regex như cơ chế duy nhất.

### Ví dụ bắt MailException

~~~java
try {
    mailSender.send(message);
} catch (MailException exception) {
    // Ghi nhận lỗi đã chuẩn hóa và quyết định retry/failure.
    throw new MailDeliveryException(
            "Unable to submit email", exception);
}
~~~

Đây là ví dụ bọc lỗi ở tầng transport. Nếu ném lại exception, caller hoặc worker phải quyết định cập nhật trạng thái. Với optional email, caller có thể ghi nhận lỗi rồi tiếp tục nghiệp vụ; với required durable email, worker cần đưa record vào retry hoặc trạng thái FAILED.

### Không bắt lỗi rồi giả vờ gửi thành công

Không nên:

~~~java
try {
    mailSender.send(message);
} catch (MailException exception) {
    log.warn("Email failed", exception);
}

return "SUCCESS";
~~~

Cách này làm mất khác biệt giữa SUBMITTED và FAILED. Với email bắt buộc, thông điệp có thể biến mất mà không ai biết. Với email tùy chọn, vẫn cần ghi nhận failure/suppression để đo chất lượng hệ thống.

## 12. Retry, backoff và dead-letter

Retry nên dựa vào loại lỗi và chính sách category.

### Backoff

Không retry liên tục mỗi vài mili giây. Một chiến lược có thể dùng exponential backoff:

~~~text
delay = min(maxDelay, initialDelay * 2^attempt) + jitter
~~~

Ví dụ lịch thử:

| Lần thử | Thời gian chờ minh họa |
| --- | --- |
| 1 | Ngay sau khi job được claim |
| 2 | 30 giây |
| 3 | 2 phút |
| 4 | 10 phút |
| 5 | 30 phút |

Các giá trị chỉ là ví dụ. Cần điều chỉnh theo SMTP provider, độ khẩn cấp, lượng email và thời hạn thông điệp.

### Chính sách theo loại email

| Category | Retry policy gợi ý |
| --- | --- |
| Security required | Nhanh nhưng có giới hạn; có cảnh báo và kênh thay thế khi không gửi được |
| Transactional required | Retry bền vững, có thể kéo dài theo SLA; không âm thầm bỏ |
| Product update optional | Retry giới hạn; hủy khi hết hạn hoặc preference thay đổi |
| Marketing optional | Tôn trọng campaign expiry, suppression và frequency cap; có thể bỏ qua lỗi vĩnh viễn |

### Dead-letter hoặc trạng thái cần xử lý

Sau số lần thử tối đa, không xóa record. Đưa nó vào trạng thái FAILED/DEAD_LETTER với notification ID, category, template key/version, số lần thử, mã lỗi cuối cùng đã chuẩn hóa, thời điểm lỗi và thông tin correlation.

Không lưu credential, body nhạy cảm hoặc toàn bộ SMTP transcript nếu không cần. Với email bắt buộc, trạng thái dead-letter cần được theo dõi và có quy trình replay sau khi sửa nguyên nhân. Với email tùy chọn, có thể đóng job theo policy.

## 13. Idempotency và nguy cơ gửi trùng

Worker bất đồng bộ có thể gửi cùng một email nhiều lần nếu:

- Hai worker cùng claim một outbox record.
- Worker gửi thành công nhưng process dừng trước khi cập nhật SUBMITTED.
- SMTP relay chấp nhận email nhưng response bị mất trên mạng.
- Queue giao message ít nhất một lần và consumer không deduplicate.
- Job bị replay thủ công mà không kiểm tra trạng thái cũ.

SMTP không cung cấp một cơ chế idempotency phổ quát để bảo đảm “đúng một lần” end-to-end. Header Message-ID có thể giúp nhận diện message nhưng không buộc mọi mailbox/provider loại bỏ duplicate.

### Dùng notification ID làm idempotency key nội bộ

Ví dụ khóa duy nhất:

~~~text
notification_id = ORDER_CONFIRMED:order-184:recipient-42
~~~

Database có thể đặt unique constraint cho khóa nghiệp vụ này để không tạo nhiều outbox record cho cùng sự kiện/recipient. Worker claim record bằng locking/lease và lưu attempt state.

### Xử lý trường hợp không chắc chắn

Nếu kết nối bị ngắt sau khi client đã gửi DATA nhưng trước khi nhận phản hồi cuối, ứng dụng có thể không biết relay đã nhận hay chưa. Retry có thể tạo duplicate. Các lựa chọn:

- Dùng provider API có idempotency key nếu có.
- Lưu trạng thái SUBMISSION_UNKNOWN và xử lý theo policy.
- Dùng notification ID và correlation để phát hiện duplicate ở tầng ứng dụng.
- Chấp nhận at-least-once với khả năng gửi trùng nhỏ, nếu nghiệp vụ cho phép.

Không tuyên bố hệ thống bảo đảm exactly-once chỉ vì outbox có unique key. Outbox bảo đảm lưu yêu cầu gửi cùng transaction; nó không tự giải quyết sự không chắc chắn sau khi SMTP relay nhận dữ liệu.

### Tránh tạo mã OTP mới ở mỗi lần retry

Với OTP hoặc reset token, retry gửi nên sử dụng cùng challenge/token còn hiệu lực theo policy, không tạo vô hạn token mới. Token phải có hạn dùng, giới hạn số lần thử, khả năng thu hồi và không được ghi vào log. Nếu challenge hết hạn, tạo challenge mới theo quy trình nghiệp vụ.

## 14. Trạng thái gửi email nên phản ánh điều gì?

Một hệ thống có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| CREATED | Yêu cầu gửi được tạo |
| SUPPRESSED | Không gửi vì preference, consent hoặc suppression policy |
| PENDING | Đang chờ worker |
| PROCESSING | Worker đang xử lý |
| RENDERED | Nội dung đã được render |
| SUBMITTED | SMTP relay đã chấp nhận thông điệp |
| RETRY_PENDING | Lỗi tạm thời, chờ thử lại |
| FAILED | Lỗi vĩnh viễn hoặc vượt chính sách retry |
| EXPIRED | Email tùy chọn hết thời hạn |
| CANCELLED | Yêu cầu bị hủy trước khi submit |

Không phải ứng dụng nào cũng cần tất cả trạng thái. Hãy chọn trạng thái đủ để trả lời:

- Yêu cầu gửi đã được tạo chưa?
- Email có bị bỏ qua do preference không?
- Có worker đang xử lý không?
- Nội dung render có thành công không?
- SMTP relay đã chấp nhận chưa?
- Có cần retry hoặc can thiệp không?

### Submitted không có nghĩa delivered

Khi JavaMailSender.send trả về bình thường, ứng dụng thường chỉ biết rằng thao tác submit qua SMTP đã hoàn tất theo phản hồi nhận được. Relay có thể tiếp tục xử lý sau đó. Email có thể bị bounce, vào spam, bị trì hoãn hoặc bị mailbox đích từ chối.

Nếu cần trạng thái delivered/bounced, phải tích hợp provider event, bounce processing hoặc webhook tương ứng. Không suy ra “đã đến inbox” từ việc send() không ném exception.

## 15. Ví dụ điều phối email bắt buộc và tùy chọn

Một lớp điều phối có thể phân nhánh theo policy:

~~~java
@Service
public class ApplicationMailService {

    private final RequiredMailService requiredMailService;
    private final OptionalMailService optionalMailService;
    private final MailPolicy mailPolicy;
    private final PreferenceService preferenceService;

    public ApplicationMailService(
            RequiredMailService requiredMailService,
            OptionalMailService optionalMailService,
            MailPolicy mailPolicy,
            PreferenceService preferenceService) {
        this.requiredMailService = requiredMailService;
        this.optionalMailService = optionalMailService;
        this.mailPolicy = mailPolicy;
        this.preferenceService = preferenceService;
    }

    public void requestEmail(
            MailCategory category,
            String recipientId,
            MailPayload payload) {

        EmailPreferences preferences =
                preferenceService.getFor(recipientId);

        MailDecision decision = mailPolicy.decide(
                category, preferences);

        switch (decision) {
            case SUPPRESS -> optionalMailService.recordSuppressed(
                    category, recipientId, payload);
            case REQUIRE_BLOCKING_DELIVERY ->
                    requiredMailService.sendBlocking(
                            category, recipientId, payload);
            case REQUIRE_DURABLE_DELIVERY ->
                    requiredMailService.enqueueDurably(
                            category, recipientId, payload);
            case ALLOW ->
                    optionalMailService.enqueueBestEffort(
                            category, recipientId, payload);
        }
    }
}
~~~

Các lớp và DTO trong ví dụ là thành phần do ứng dụng định nghĩa. Trong hệ thống thực, không nên tải preference chỉ bằng email address nếu địa chỉ có thể được chia sẻ hoặc chưa xác minh; hãy dùng recipient/user ID và kiểm tra quyền. RequiredMailService không nên coi mọi category bắt buộc là synchronous; ví dụ policy trên chỉ dùng blocking cho loại được xác định rõ.

### Tại sao tách RequiredMailService và OptionalMailService?

Hai service có thể dùng chung renderer và transport, nhưng chính sách khác nhau:

- RequiredMailService cần lưu trạng thái, retry, cảnh báo và không âm thầm loại bỏ thông điệp.
- OptionalMailService cần kiểm tra consent/preferences, unsubscribe, suppression, frequency cap và expiry.
- Cả hai có thể dùng chung JavaMailSender adapter, MIME builder và template engine.

Việc tách lớp không bắt buộc trong mọi dự án. Điều quan trọng là các chính sách khác nhau phải được biểu diễn rõ và có thể kiểm thử.

## 16. Cấu hình và giới hạn SMTP

Spring Boot có thể cấu hình mail sender:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: configured-smtp-user
    password: supplied-by-secret-store
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Đây là cấu hình ví dụ cho SMTP submission với STARTTLS. Host, port và các thuộc tính bảo mật cần theo nhà cung cấp thực tế. Credential lấy từ secret/environment, không commit vào repository.

### Timeout có ý nghĩa gì?

- Connection timeout giới hạn thời gian thiết lập kết nối.
- Read timeout giới hạn thời gian chờ dữ liệu phản hồi.
- Write timeout giới hạn thời gian ghi dữ liệu.

Giới hạn này đặc biệt quan trọng với gửi đồng bộ, vì request có thể bị giữ trong thời gian SMTP chậm. Với worker bất đồng bộ, timeout giúp giải phóng worker và cho phép policy retry quyết định bước tiếp theo.

### Rate limit và quota

SMTP provider có thể giới hạn số thư mỗi giây, mỗi ngày hoặc theo tài khoản. Worker nên có rate limit và concurrency phù hợp. Nếu provider trả lỗi tạm thời do quota/rate, retry cần backoff; không tăng worker vô hạn.

Email tùy chọn thường cần frequency cap theo user/campaign. Email bắt buộc có thể có mức ưu tiên cao hơn trong queue nhưng vẫn phải tuân theo giới hạn vận hành và chính sách provider.

## 17. Bảo mật và dữ liệu trong email

Email không phải kênh phù hợp để gửi mọi loại bí mật. Dù là email bắt buộc, nội dung nên giới hạn ở thông tin cần thiết.

### OTP và reset link

- Token có thời hạn ngắn và chỉ dùng theo đúng mục đích.
- Không ghi token vào log hoặc metrics.
- Không gửi token qua nhiều recipient không được phép.
- Giới hạn số lần yêu cầu và xác minh.
- Có khả năng thu hồi challenge.
- Dùng HTTPS cho link.
- Không xác nhận thao tác nhạy cảm chỉ vì email đã được submit.

### Dữ liệu giao dịch

- Chỉ đưa dữ liệu mà recipient được quyền xem.
- Không gửi thông tin thanh toán nhạy cảm đầy đủ nếu không cần.
- Attachment cần qua kiểm tra/quét theo policy.
- URL tài liệu cần authorization và thời hạn phù hợp.
- Kiểm tra địa chỉ recipient trước khi gửi.

### Email tùy chọn

- Không gửi marketing nếu consent/preferences không cho phép.
- Không để unsubscribe link bị mất trong template.
- Không dùng dữ liệu nhạy cảm để cá nhân hóa ngoài mục đích được phép.
- Hạn chế theo dõi mở/click theo chính sách riêng tư.
- Không gửi lại chiến dịch đã hết hạn hoặc đã bị hủy.

### Log và audit

Nên log notification ID, category, template version, trạng thái, số lần thử và mã lỗi đã chuẩn hóa. Tránh log body email, OTP, reset token, password, attachment bytes hoặc URL có token.

## 18. Kiểm thử chính sách email bắt buộc và tùy chọn

Kiểm thử không chỉ xác nhận JavaMailSender được gọi. Cần kiểm tra **khi nào được gọi, khi nào không được gọi và lỗi ảnh hưởng thế nào đến nghiệp vụ**.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Required email render và submit thành công | Trạng thái SUBMITTED hoặc trạng thái phù hợp |
| Required email SMTP tạm lỗi | Outbox RETRY_PENDING, không mất yêu cầu |
| Required email lỗi vĩnh viễn | FAILED/alert hoặc luồng thay thế theo policy |
| OTP email không gửi được | Không đánh dấu xác thực thành công |
| Order email lỗi sau khi order commit | Order vẫn tồn tại; email được retry |
| Optional marketing bị unsubscribe | SUPPRESSED; không gọi JavaMailSender |
| Preference đổi sau enqueue | Worker kiểm tra lại và suppress |
| Optional email SMTP lỗi | Ghi nhận lỗi; không làm thao tác chính thất bại |
| Campaign hết hạn trong queue | EXPIRED; không gửi muộn |
| Worker chạy lại cùng outbox ID | Không tạo thêm notification nghiệp vụ ngoài policy |
| SMTP phản hồi không rõ sau DATA | Trạng thái/retry được xử lý theo chính sách duplicate |

### Test service tùy chọn không gửi khi preference tắt

~~~java
@Test
void doesNotSendMarketingWhenUserOptedOut() {
    when(preferenceService.getFor("user-42"))
            .thenReturn(new EmailPreferences(false, false, false));

    applicationMailService.requestEmail(
            MailCategory.MARKETING_OPTIONAL,
            "user-42",
            payload);

    verify(optionalMailService).recordSuppressed(
            eq(MailCategory.MARKETING_OPTIONAL),
            eq("user-42"),
            eq(payload));
    verifyNoInteractions(requiredMailService);
}
~~~

Đây là test minh họa dùng Mockito. Tùy cách thiết kế service, có thể kiểm tra repository/outbox status thay vì gọi một method recordSuppressed riêng.

### Test lỗi SMTP không làm rollback giao dịch chính

Với transactional outbox, test nên xác nhận:

1. Domain entity được lưu.
2. Outbox record được lưu trong cùng transaction.
3. Worker gọi SMTP và nhận lỗi.
4. Outbox chuyển sang RETRY_PENDING hoặc trạng thái phù hợp.
5. Domain entity vẫn còn sau lỗi gửi.

Không mock transaction rồi chỉ assert một method được gọi; cần integration test với database test phù hợp để chứng minh tính nhất quán của transaction nếu đây là yêu cầu quan trọng.

### Test transactional event có giới hạn gì?

Test @TransactionalEventListener nên kiểm tra listener chỉ chạy sau commit. Nhưng không nên coi test này chứng minh event được lưu bền vững qua process restart. Nếu yêu cầu không mất thông điệp, cần test outbox/queue persistence.

## 19. Các lỗi thiết kế thường gặp

### 19.1. Gửi email tùy chọn trong cùng transaction với thao tác chính

Một chiến dịch marketing bị SMTP lỗi có thể làm đăng ký tài khoản rollback. Hãy tách notification khỏi transaction chính và xử lý nền.

### 19.2. Gửi email bắt buộc nhưng không lưu trạng thái

Nếu SMTP lỗi và exception bị bỏ qua, hệ thống không biết email đã được xử lý hay chưa. Dùng outbox hoặc trạng thái notification để theo dõi.

### 19.3. Gọi SMTP trước khi transaction commit

Người nhận có thể nhận xác nhận cho dữ liệu sau đó bị rollback. Gửi sau commit hoặc dùng transactional outbox.

### 19.4. Dùng @Async và nghĩ rằng đã có durable queue

@Async chạy tác vụ ở executor khác nhưng không tự lưu công việc bền vững. Process dừng có thể làm mất task chưa chạy. Dùng outbox/message broker nếu cần bảo đảm.

### 19.5. Chỉ kiểm tra consent lúc enqueue

Người dùng có thể unsubscribe trước khi worker gửi. Kiểm tra lại preference ngay trước submit.

### 19.6. Một boolean cho mọi loại email

Trường emailEnabled=true/false không đủ để biểu diễn security, transactional, newsletter và marketing. Dùng preference theo category và policy rõ ràng.

### 19.7. Retry vô hạn

Lỗi địa chỉ sai hoặc template sai không tự hết. Phân loại transient/permanent, giới hạn số lần thử và đưa lỗi cần xử lý vào dead-letter.

### 19.8. Retry tạo token mới

Người dùng có thể nhận nhiều OTP/reset link cùng lúc và không biết token nào còn hiệu lực. Retry cùng challenge còn hiệu lực theo policy; tạo challenge mới chỉ khi quy trình yêu cầu.

### 19.9. Coi send() thành công là email đã đến inbox

JavaMailSender chỉ cho biết kết quả submit theo phản hồi SMTP. Cần provider events/bounce handling nếu cần delivery status.

### 19.10. Không chống duplicate

Worker có thể gửi lại sau khi process dừng giữa SMTP acceptance và cập nhật database. Dùng idempotency key nội bộ, claim/lease và hiểu rõ khả năng duplicate.

### 19.11. Đưa nội dung marketing vào email giao dịch

Điều này làm thông điệp khó phân loại, có thể gây nhầm lẫn cho người nhận và ảnh hưởng chính sách consent. Tách email giao dịch và chiến dịch.

### 19.12. Xóa job lỗi mà không audit

Email bắt buộc có thể bị mất vĩnh viễn. Giữ trạng thái cuối, mã lỗi, notification ID và quy trình replay.

## 20. Quy trình thiết kế từ đầu

Khi thêm một loại email mới, có thể thực hiện theo thứ tự:

1. Xác định mục đích và category: security, transactional, product update hay marketing.
2. Xác định điều kiện gửi, consent/preferences và người nhận hợp lệ.
3. Quyết định email có phải điều kiện để hoàn tất thao tác hiện tại không.
4. Chọn delivery mode: blocking, durable async hay best-effort.
5. Xác định dữ liệu cần lưu và template version.
6. Tạo HTML/text template và view model.
7. Xác định trạng thái, retry policy, expiry và dead-letter behavior.
8. Tạo idempotency key/notification ID.
9. Tích hợp JavaMailSender qua một adapter.
10. Viết test cho thành công, lỗi, suppression, retry và duplicate.
11. Thêm metrics, log và alert theo category.
12. Kiểm tra privacy, bảo mật và chính sách người nhận.

### Ví dụ quyết định cho bốn loại email

| Loại email | Category | Giao | Khi lỗi |
| --- | --- | --- | --- |
| OTP đăng nhập | SECURITY_REQUIRED | Blocking hoặc quy trình gửi có phản hồi tức thời | Không cho xác thực hoàn tất; cho retry có giới hạn |
| Xác nhận đơn hàng | TRANSACTIONAL_REQUIRED | Durable async qua outbox | Đơn hàng vẫn commit; retry và theo dõi |
| Thông báo tính năng mới | PRODUCT_UPDATE_OPTIONAL | Best-effort/queue có expiry | Suppress hoặc retry giới hạn; không chặn chức năng |
| Newsletter | MARKETING_OPTIONAL | Queue có consent check | Không gửi nếu unsubscribe; job có thể hết hạn |

Đây là một bộ lựa chọn minh họa, không phải quy tắc cố định cho mọi hệ thống. Nếu sản phẩm có yêu cầu khác, thay đổi policy mà vẫn giữ rõ sự phân biệt giữa nghiệp vụ và transport.

## 21. Câu hỏi tự kiểm tra

**1. Email bắt buộc có luôn phải gửi đồng bộ không?**

Không. “Bắt buộc” có nghĩa thông điệp phải được xử lý theo policy. Email giao dịch thường có thể lưu trong outbox và gửi nền để không giữ transaction database chờ SMTP.

**2. Email tùy chọn có được gửi dù người dùng đã unsubscribe không?**

Không. Kiểm tra preference/consent theo category trước khi tạo job và kiểm tra lại ngay trước khi gửi.

**3. Nếu email xác nhận đơn hàng lỗi SMTP, có nên rollback đơn hàng không?**

Thông thường không. Đơn hàng là giao dịch chính; email cần được lưu và retry độc lập. Chỉ chặn khi email thực sự là điều kiện của chính bước nghiệp vụ đó.

**4. @TransactionalEventListener(AFTER_COMMIT) có bảo đảm không mất event khi process dừng không?**

Không. Nó giúp chạy sau commit nhưng event trong bộ nhớ không phải durable queue. Transactional outbox lưu yêu cầu gửi cùng transaction sẽ phù hợp hơn khi cần độ bền.

**5. @Async có thay thế outbox không?**

Không. @Async chuyển việc xử lý sang executor khác nhưng không tự lưu task bền vững hoặc cung cấp retry/audit.

**6. JavaMailSender.send() thành công chứng minh điều gì?**

Thông thường chỉ chứng minh SMTP submission đã được chấp nhận theo phản hồi nhận được. Nó không chứng minh email đã đến inbox hoặc được đọc.

**7. Vì sao phải kiểm tra preference hai lần?**

Vì người dùng có thể thay đổi lựa chọn sau khi job được enqueue nhưng trước khi worker gửi.

**8. Có thể retry mọi MailException không?**

Không. Lỗi kết nối tạm thời có thể retry; credential sai, địa chỉ không hợp lệ hoặc lỗi template cần xử lý nguyên nhân trước.

**9. Outbox bảo đảm exactly-once không?**

Không. Nó giúp lưu yêu cầu gửi cùng transaction. Duplicate vẫn có thể xảy ra khi SMTP relay đã nhận nhưng ứng dụng không nhận được phản hồi hoặc worker dừng trước khi cập nhật trạng thái.

**10. Vì sao cần idempotency key?**

Để nhận diện cùng một thông điệp nghiệp vụ, tránh tạo nhiều outbox record hoặc gửi lại ngoài chính sách khi worker/queue xử lý lặp.

**11. Có nên lưu toàn bộ nội dung email trong outbox?**

Không bắt buộc. Có thể lưu payload và template version; snapshot đã render chỉ nên lưu khi cần tái lập/audit và có chính sách bảo vệ dữ liệu phù hợp.

**12. Email marketing hết hạn trong queue nên xử lý thế nào?**

Đánh dấu EXPIRED hoặc SUPPRESSED và không gửi chiến dịch muộn. Không retry vô hạn một nội dung không còn giá trị.

## Kết luận

**Xử lý email bắt buộc và email tùy chọn cần hai chính sách nghiệp vụ rõ ràng, dù cả hai có thể dùng chung Spring JavaMailSender.** Email bảo mật và giao dịch cần được theo dõi đến trạng thái phù hợp, có retry và không bị âm thầm bỏ; email tùy chọn phải tôn trọng preference/consent, unsubscribe, suppression và thời hạn chiến dịch. Chỉ chặn thao tác chính khi email thực sự là điều kiện của bước đó. Với thông báo giao dịch sau commit, transactional outbox giúp lưu yêu cầu gửi cùng dữ liệu nghiệp vụ và xử lý SMTP ở worker; với OTP cần phản hồi tức thời, có thể dùng luồng blocking nhưng phải kiểm soát timeout và trạng thái challenge. Kết hợp idempotency, retry có backoff, trạng thái rõ ràng và kiểm thử lỗi giúp hệ thống gửi đúng loại email, đúng thời điểm và đúng người nhận.
