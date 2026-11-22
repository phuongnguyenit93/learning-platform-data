# Rủi ro transaction commit nhưng gửi mail thất bại trong Spring Framework Mail

Gửi email là một side effect bên ngoài database. Khi ứng dụng cập nhật đơn hàng, lưu trạng thái giao dịch hoặc tạo tài khoản rồi gửi email thông báo, hai thao tác thường diễn ra trên hai hệ thống độc lập: database và SMTP provider. Database có transaction, nhưng SMTP không tham gia transaction đó. Vì vậy, không có một lệnh rollback chung có thể hoàn tác cả việc ghi dữ liệu lẫn việc gửi email.

Điều này tạo ra một rủi ro quan trọng: **transaction database có thể commit thành công nhưng email không được gửi**, hoặc email đã được SMTP chấp nhận nhưng transaction database sau đó rollback. Cả hai tình huống đều có thể làm trạng thái nghiệp vụ và thông báo gửi tới người dùng không nhất quán.

Trong Spring Framework Mail, việc gọi **JavaMailSender.send(...)** thường rất đơn giản. Phần khó nằm ở việc chọn đúng thời điểm gửi, quyết định điều gì xảy ra khi SMTP lỗi, và bảo đảm yêu cầu gửi không biến mất khi ứng dụng gặp sự cố. Bài học này giải thích các failure window, cách dùng transaction event, giới hạn của **@TransactionalEventListener** và cách triển khai transactional outbox khi cần độ tin cậy cao.

## 1. Database transaction và SMTP là hai hệ thống độc lập

Xét use case xác nhận đơn hàng:

1. Đọc đơn hàng đang chờ xác nhận.
2. Chuyển trạng thái sang CONFIRMED.
3. Lưu thay đổi vào database.
4. Gửi email xác nhận cho khách hàng.

Database có thể commit hoặc rollback các câu lệnh SQL trong transaction. SMTP server lại xử lý việc nhận message theo giao thức riêng. Việc SMTP chấp nhận email không nằm trong transaction của database.

~~~text
Ứng dụng
   |
   +---- Database transaction
   |         |
   |         +--> UPDATE order
   |         +--> COMMIT / ROLLBACK
   |
   +---- SMTP operation
             |
             +--> Submit MIME message
             +--> SMTP response
~~~

Hai hệ thống không chia sẻ một transaction manager. Nếu database rollback, SMTP không tự thu hồi email đã nhận. Nếu SMTP từ chối email, database không tự biết phải rollback hay giữ nguyên trạng thái nghiệp vụ.

Đây là bài toán phối hợp side effect giữa nhiều hệ thống. Nó xuất hiện với email, SMS, push notification, webhook, thanh toán, publish message và các lời gọi HTTP tới dịch vụ bên ngoài.

## 2. Hai failure window cơ bản

Có hai cách gọi mail phổ biến trong một method có transaction, và cả hai đều có rủi ro.

### Trường hợp A: Gửi email trước khi transaction commit

~~~java
@Transactional
public void confirmOrder(Long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    mailDelivery.sendConfirmation(order);
}
~~~

Luồng:

~~~text
BEGIN DB TRANSACTION
        |
        v
Update order = CONFIRMED
        |
        v
SMTP nhận email thành công
        |
        v
Database COMMIT thất bại
        |
        v
Database ROLLBACK
~~~

Khách hàng có thể nhận email nói rằng đơn hàng đã được xác nhận, trong khi database vẫn ghi đơn hàng ở trạng thái PENDING. Email đã gửi không thể được hoàn tác bằng rollback SQL.

Một biến thể khác: SMTP gửi thành công, nhưng sau đó một câu lệnh database hoặc bước xử lý trước commit bị lỗi. Kết quả vẫn là email đã ra ngoài trong khi thay đổi nghiệp vụ không được commit.

### Trường hợp B: Commit database trước, sau đó gửi email

~~~java
@Transactional
public void confirmOrder(Long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow();

    order.confirm();
    orderRepository.save(order);
}

// Một bước khác gửi email sau khi method trả về.
mailDelivery.sendConfirmation(orderId);
~~~

Luồng:

~~~text
BEGIN DB TRANSACTION
        |
        v
Update order = CONFIRMED
        |
        v
DATABASE COMMIT thành công
        |
        v
Ứng dụng gọi SMTP
        |
        v
SMTP timeout / từ chối / mất kết nối
        |
        v
Order vẫn CONFIRMED, email chưa được gửi
~~~

Ở trường hợp này, dữ liệu nghiệp vụ đúng nhưng khách hàng không nhận thông báo. Nếu email là một phần quan trọng của quy trình, hệ thống cần biết yêu cầu gửi đang thất bại và có cách xử lý tiếp.

### So sánh hai rủi ro

| Thời điểm gửi | Khi SMTP thành công nhưng DB rollback | Khi DB commit nhưng SMTP thất bại |
| --- | --- | --- |
| Gửi trước commit | Có thể gửi thông báo sai trạng thái | Lỗi SMTP có thể làm transaction rollback tùy exception |
| Gửi sau commit | Không còn rủi ro SMTP chạy trước commit | Thay đổi nghiệp vụ đã lưu nhưng thông báo có thể bị mất |

Không có cách sắp xếp hai lệnh tuần tự nào khiến database và SMTP trở thành một transaction nguyên tử. Cần chọn chiến lược dựa trên mức độ quan trọng của email.

## 3. Vì sao không nên gửi SMTP bên trong transaction dài?

Một transaction database nên tập trung vào thao tác dữ liệu cần commit cùng nhau. Gọi SMTP trong transaction có thể khiến connection và lock database bị giữ trong lúc chờ network.

Các vấn đề thường gặp:

- SMTP server chậm làm transaction kéo dài.
- Database connection bị giữ trong thời gian gửi email.
- Lock trên đơn hàng hoặc các row liên quan được giữ lâu hơn.
- Throughput giảm khi nhiều request cùng gửi mail.
- Timeout SMTP có thể làm transaction rollback dù thay đổi nghiệp vụ đã hợp lệ.
- Email đã được chấp nhận nhưng database commit có thể thất bại sau đó.

Ví dụ, nếu SMTP mất 8 giây mới trả lời, transaction xác nhận đơn hàng có thể giữ connection thêm 8 giây. Với lượng request lớn, connection pool có thể cạn dù database query vốn rất nhanh.

Một cách tổ chức tốt là hoàn tất transaction dữ liệu trước, sau đó xử lý việc gửi ở một bước riêng. Tuy nhiên, chỉ chuyển lời gọi ra sau transaction vẫn chưa giải quyết được việc ứng dụng crash đúng khoảng giữa commit và gửi.

## 4. Cẩn thận với quy tắc rollback của Spring

Spring transaction mặc định rollback khi method kết thúc bằng **RuntimeException** hoặc **Error**. Checked exception thường không kích hoạt rollback theo mặc định, trừ khi cấu hình **rollbackFor** hoặc quy tắc tương ứng.

Trong luồng gửi mail, **MailException** của Spring là runtime exception, còn một số API Jakarta Mail như **MessagingException** là checked exception. Adapter có thể wrap lỗi checked thành application runtime exception.

Ví dụ:

~~~java
@Transactional
public void confirmOrder(Long orderId) {
    Order order = loadOrder(orderId);
    order.confirm();
    orderRepository.save(order);

    mailDelivery.sendConfirmation(order);
}
~~~

Nếu adapter ném **MailDeliveryException extends RuntimeException**, transaction thường rollback theo mặc định. Nếu exception checked được ném ra và không có rollback rule, transaction có thể vẫn commit tùy cách exception được xử lý.

Có thể chỉ định rõ:

~~~java
@Transactional(rollbackFor = MessagingException.class)
public void confirmOrder(Long orderId) throws MessagingException {
    // Thay đổi dữ liệu và gửi mail.
}
~~~

Nhưng quy tắc rollback chỉ điều khiển database transaction. Nó không thể thu hồi email đã được SMTP chấp nhận. Nếu email gửi thành công rồi transaction gặp lỗi commit, inconsistency vẫn còn.

Đừng dùng rollback rule như một cơ chế đảm bảo atomicity giữa database và SMTP.

## 5. Dùng @TransactionalEventListener(AFTER_COMMIT)

Spring cung cấp **@TransactionalEventListener** để xử lý một application event theo phase của transaction. Với email thông báo sau khi đơn hàng commit, có thể dùng phase **AFTER_COMMIT**.

Event:

~~~java
public record OrderConfirmedEvent(
    Long orderId,
    String customerEmail,
    String orderCode
) {}
~~~

Publish event bên trong transaction:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public OrderService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.confirm();
        orderRepository.save(order);

        eventPublisher.publishEvent(
            new OrderConfirmedEvent(
                order.getId(),
                order.getCustomerEmail(),
                order.getCode()
            )
        );
    }
}
~~~

Listener gửi email sau khi transaction commit:

~~~java
@Component
public class OrderMailListener {

    private final OrderConfirmationMailer mailer;

    public OrderMailListener(OrderConfirmationMailer mailer) {
        this.mailer = mailer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailer.sendConfirmation(
            event.customerEmail(),
            event.orderCode()
        );
    }
}
~~~

Khi transaction rollback, listener phase AFTER_COMMIT không được gọi. Khi transaction commit thành công, listener mới được kích hoạt. Điều này tránh gửi email trước khi trạng thái đơn hàng được commit.

### AFTER_COMMIT giải quyết điều gì?

- Email chỉ được yêu cầu gửi sau khi transaction thành công.
- Nếu transaction rollback, event listener không chạy.
- Logic gửi mail được tách khỏi method cập nhật dữ liệu.
- Use case có thể phát event mang ý nghĩa nghiệp vụ, listener quyết định cách phản ứng.

### AFTER_COMMIT không bảo đảm event được lưu bền vững

Application event mặc định là sự kiện trong bộ nhớ của tiến trình. Có một khoảng trống:

~~~text
Database COMMIT thành công
        |
        v
Process bị kill / máy chủ mất điện
        |
        v
Listener chưa kịp thực thi
        |
        v
Không có email và cũng không có record bền vững để retry
~~~

Nếu tiến trình dừng sau commit nhưng trước khi listener gửi mail, event đã mất cùng bộ nhớ của tiến trình. Database không có bản ghi nào cho biết cần gửi email.

Ngoài ra, listener có thể chạy nhưng SMTP thất bại. Transaction database đã commit nên exception của listener không thể rollback thay đổi đã commit.

Vì vậy, **@TransactionalEventListener(AFTER_COMMIT)** phù hợp với side effect best-effort hoặc các thông báo có thể chấp nhận mất trong một failure window nhỏ. Với email giao dịch quan trọng, cần lưu yêu cầu gửi bền vững.

## 6. Các phase của transactional event

**@TransactionalEventListener** hỗ trợ các phase:

| Phase | Thời điểm | Rủi ro/ý nghĩa |
| --- | --- | --- |
| BEFORE_COMMIT | Trước khi transaction commit | Email có thể được gửi dù commit sau đó thất bại |
| AFTER_COMMIT | Sau khi transaction commit thành công | Tránh gửi trước commit, nhưng event trong bộ nhớ có thể mất nếu process crash |
| AFTER_ROLLBACK | Sau khi transaction rollback | Dùng cho xử lý phụ thuộc rollback, thường không gửi email xác nhận thành công |
| AFTER_COMPLETION | Sau khi transaction hoàn tất, commit hoặc rollback | Phải tự kiểm tra trạng thái hoàn tất nếu hành vi khác nhau |

Nếu không chỉ định phase, mặc định là AFTER_COMMIT. Listener transactional chỉ được gọi khi có transaction phù hợp, trừ khi bật **fallbackExecution**. Không nên bật fallback chỉ để listener chạy trong mọi tình huống mà chưa xác định rõ hành vi khi không có transaction.

### Kết hợp với @Async

Có thể chạy listener bất đồng bộ:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Component
public class OrderMailListener {

    private final OrderConfirmationMailer mailer;

    public OrderMailListener(OrderConfirmationMailer mailer) {
        this.mailer = mailer;
    }

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailer.sendConfirmation(
            event.customerEmail(),
            event.orderCode()
        );
    }
}
~~~

Cách này giảm thời gian xử lý của request vì phần gửi được thực hiện trên executor. Nhưng event vẫn chỉ nằm trong bộ nhớ; process crash có thể làm mất event. Nếu executor đầy, bị shutdown hoặc listener lỗi, cần có cơ chế quan sát và xử lý lỗi. **@Async** không tự biến event thành message bền vững.

Với listener bất đồng bộ, exception không tự quay lại request đã hoàn thành. Cần cấu hình xử lý exception của executor và metrics phù hợp.

## 7. Transactional outbox là gì?

Transactional outbox lưu **ý định gửi thông báo** vào database trong cùng transaction với thay đổi nghiệp vụ. Một worker độc lập đọc các record đã commit rồi gửi email.

Thay vì thực hiện:

~~~text
UPDATE order
COMMIT
Gửi email
~~~

ứng dụng thực hiện:

~~~text
BEGIN TRANSACTION
    UPDATE order
    INSERT mail_outbox
COMMIT

Worker:
    SELECT mail_outbox
    Gửi email
    UPDATE mail_outbox status
~~~

Cả cập nhật đơn hàng và insert outbox row nằm trong cùng một transaction database. Vì vậy:

- Nếu transaction rollback, cả thay đổi đơn hàng và outbox row đều rollback.
- Nếu transaction commit, cả thay đổi đơn hàng và yêu cầu gửi đều được lưu.
- Nếu process crash sau commit, worker vẫn có thể tìm thấy outbox row khi ứng dụng khởi động lại.
- Nếu SMTP tạm lỗi, worker có thể retry dựa trên record còn tồn tại.

Outbox giải quyết việc **không mất yêu cầu gửi giữa database commit và việc enqueue**. Nó không tạo transaction nguyên tử với SMTP và không tự bảo đảm email chỉ được gửi đúng một lần.

## 8. Tạo bảng outbox

Một schema cơ bản có thể như sau:

~~~sql
CREATE TABLE mail_outbox (
    id                  UUID PRIMARY KEY,
    idempotency_key     VARCHAR(200) NOT NULL UNIQUE,
    event_type          VARCHAR(120) NOT NULL,
    aggregate_id        VARCHAR(120) NOT NULL,
    payload             JSONB NOT NULL,
    status              VARCHAR(30) NOT NULL,
    attempts            INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_by           VARCHAR(120),
    locked_until        TIMESTAMPTZ,
    provider_message_id VARCHAR(255),
    last_error          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at        TIMESTAMPTZ
);

CREATE INDEX idx_mail_outbox_pending
    ON mail_outbox (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

Ý nghĩa các trường:

| Trường | Mục đích |
| --- | --- |
| id | Định danh duy nhất của yêu cầu gửi |
| idempotency_key | Khóa ngăn tạo nhiều outbox record cho cùng một sự kiện nghiệp vụ |
| event_type | Loại thông báo, ví dụ ORDER_CONFIRMED |
| aggregate_id | ID đơn hàng hoặc đối tượng nghiệp vụ liên quan |
| payload | Dữ liệu cần thiết để dựng email |
| status | Trạng thái xử lý hiện tại |
| attempts | Số lần worker đã thử gửi |
| next_attempt_at | Thời điểm sớm nhất được phép thử tiếp |
| locked_by | Worker đang giữ quyền xử lý record |
| locked_until | Hạn hết lease để worker khác có thể thu hồi |
| provider_message_id | ID do provider trả về nếu có |
| last_error | Thông tin lỗi đã được giới hạn và làm sạch |
| created_at | Thời điểm tạo yêu cầu |
| submitted_at | Thời điểm transport xác nhận submission |

JSONB là kiểu dữ liệu PostgreSQL trong ví dụ. Với database khác, có thể dùng JSON, TEXT hoặc các cột riêng. Không cần lưu toàn bộ HTML hoặc attachment bytes trong outbox nếu payload có thể tham chiếu template và file storage an toàn.

Unique constraint trên idempotency_key giúp tránh tạo hai yêu cầu gửi cho cùng một sự kiện khi request nghiệp vụ được retry. Khóa phải phản ánh định danh sự kiện, ví dụ order ID cộng event version hoặc business event ID; không dùng một chuỗi ngẫu nhiên mới cho mỗi lần retry của cùng thao tác.

## 9. Ghi outbox trong cùng transaction với thay đổi nghiệp vụ

Ví dụ DTO payload:

~~~java
public record OrderConfirmedMailPayload(
    Long orderId,
    String orderCode,
    String customerEmail,
    String customerName,
    String locale
) {}
~~~

Service:

~~~java
@Service
public class OrderConfirmationService {

    private final OrderRepository orderRepository;
    private final MailOutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;

    public OrderConfirmationService(
            OrderRepository orderRepository,
            MailOutboxRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.confirm();
        orderRepository.save(order);

        OrderConfirmedMailPayload payload =
            new OrderConfirmedMailPayload(
                order.getId(),
                order.getCode(),
                order.getCustomerEmail(),
                order.getCustomerName(),
                "vi-VN"
            );

        MailOutboxMessage message = MailOutboxMessage.pending(
            UUID.randomUUID(),
            "ORDER_CONFIRMED:" + order.getId(),
            "ORDER_CONFIRMED",
            order.getId().toString(),
            serialize(payload)
        );

        outboxRepository.save(message);
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                "Cannot serialize mail outbox payload",
                exception
            );
        }
    }
}
~~~

Điểm quan trọng là **orderRepository.save** và **outboxRepository.save** tham gia cùng transaction manager và cùng database transaction. Nếu hai repository dùng hai datasource/transaction manager riêng, một annotation @Transactional thông thường không tự tạo atomic commit giữa chúng.

Không dùng **REQUIRES_NEW** cho thao tác insert outbox trong tình huống này. Nếu outbox commit độc lập trong khi transaction đơn hàng rollback, worker có thể gửi email cho một thay đổi chưa từng được commit.

Nếu dùng JPA, entity outbox phải được persist trong transaction đang hoạt động. Có thể cần flush để phát hiện lỗi constraint sớm, nhưng flush không phải commit; record vẫn rollback cùng transaction.

### Lưu snapshot hay chỉ lưu aggregate ID?

Payload có thể lưu dữ liệu đã chụp tại thời điểm sự kiện xảy ra, hoặc chỉ lưu order ID rồi worker đọc lại dữ liệu mới nhất.

| Cách lưu | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Snapshot payload | Email phản ánh đúng dữ liệu tại thời điểm event | Payload chứa dữ liệu cá nhân và cần quản lý retention |
| Chỉ lưu aggregate ID | Outbox nhỏ, ít dữ liệu trùng | Worker có thể đọc trạng thái mới hơn và tạo nội dung khác với sự kiện ban đầu |
| Lưu ID + version | Có thể đọc đúng phiên bản hoặc phát hiện dữ liệu đã đổi | Cần cơ chế version/history ở domain |

Với email xác nhận giao dịch, snapshot thường dễ hiểu hơn vì nội dung cần khớp với sự kiện đã commit. Chỉ lưu dữ liệu tối thiểu cần thiết; không đưa secret, token đăng nhập hoặc thông tin nhạy cảm không cần thiết vào payload. Nếu attachment lớn, lưu một file reference bất biến thay vì nhúng bytes vào outbox.

## 10. Worker đọc và claim outbox record

Worker cần bảo đảm hai instance không cùng gửi một record trong cùng thời điểm. Một cách phổ biến là claim record trong transaction ngắn bằng row lock, sau đó commit trạng thái PROCESSING trước khi gọi SMTP.

Với PostgreSQL, có thể dùng FOR UPDATE SKIP LOCKED:

~~~sql
WITH candidates AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY_WAIT')
        OR (
            status = 'PROCESSING'
            AND locked_until < CURRENT_TIMESTAMP
        )
    )
      AND next_attempt_at <= CURRENT_TIMESTAMP
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 20
)
UPDATE mail_outbox AS outbox
SET status = 'PROCESSING',
    locked_by = :workerId,
    locked_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempts = attempts + 1
FROM candidates
WHERE outbox.id = candidates.id
RETURNING outbox.*;
~~~

Đây là ví dụ SQL PostgreSQL; cú pháp và cách bind parameter cần điều chỉnh theo repository/driver. SKIP LOCKED cho phép worker khác bỏ qua các row đang được một transaction khác khóa, nhờ đó giảm tranh chấp khi có nhiều worker.

Trình tự xử lý nên là:

1. Mở transaction ngắn.
2. Claim một batch record và đặt lease.
3. Commit trạng thái PROCESSING.
4. Đóng transaction database.
5. Gửi email qua adapter.
6. Mở transaction mới để cập nhật SUBMITTED hoặc RETRY_WAIT/FAILED.

Không giữ transaction và row lock trong suốt thời gian gọi SMTP. Network có thể chậm hoặc treo, làm worker giữ database resource không cần thiết.

### Lease để xử lý worker bị dừng

Nếu worker chết khi record đang PROCESSING, lease sẽ hết hạn. Worker khác có thể claim lại record. Lease nên dài hơn thời gian gửi dự kiến và có thể gia hạn khi xử lý tác vụ dài.

Lease giúp thu hồi công việc bị bỏ dở, nhưng không giải quyết hoàn toàn việc gửi trùng. Nếu worker đầu đã gửi thành công rồi chết trước khi cập nhật trạng thái, worker sau sẽ không biết email đã được nhận.

## 11. Tách claim, gửi và cập nhật trạng thái

Một cấu trúc Spring dễ kiểm soát là dùng các bean riêng cho transaction claim và transaction cập nhật kết quả.

Claim service:

~~~java
@Service
public class MailOutboxClaimer {

    private final MailOutboxRepository repository;

    public MailOutboxClaimer(MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<MailOutboxMessage> claimBatch(
            String workerId,
            int batchSize) {
        return repository.claimAvailable(workerId, batchSize);
    }
}
~~~

Worker:

~~~java
@Component
public class MailOutboxWorker {

    private final MailOutboxClaimer claimer;
    private final MailDeliveryPort mailDelivery;
    private final MailOutboxResultService resultService;

    public MailOutboxWorker(
            MailOutboxClaimer claimer,
            MailDeliveryPort mailDelivery,
            MailOutboxResultService resultService) {
        this.claimer = claimer;
        this.mailDelivery = mailDelivery;
        this.resultService = resultService;
    }

    public void dispatch(String workerId) {
        List<MailOutboxMessage> messages =
            claimer.claimBatch(workerId, 20);

        for (MailOutboxMessage message : messages) {
            try {
                OutgoingMail mail = mapToOutgoingMail(message);
                mailDelivery.send(mail);

                resultService.markSubmitted(message.id());
            } catch (TransientMailException exception) {
                resultService.scheduleRetry(
                    message.id(),
                    exception.getMessage()
                );
            } catch (PermanentMailException exception) {
                resultService.markFailed(
                    message.id(),
                    exception.getMessage()
                );
            }
        }
    }
}
~~~

MailOutboxClaimer là bean riêng để Spring transaction proxy áp dụng cho phương thức claim. Tránh gọi một phương thức @Transactional từ một method khác trong cùng instance rồi kỳ vọng self-invocation đi qua proxy.

MailOutboxResultService nên cập nhật trạng thái bằng transaction ngắn riêng. Worker không đặt @Transactional cho toàn bộ method dispatch, vì phần gọi mail delivery phải chạy ngoài transaction claim.

Ví dụ này là cấu trúc minh họa. Việc map exception thành transient/permanent cần dựa trên provider response, loại lỗi và policy của ứng dụng.

## 12. Outbox không tự bảo đảm exactly-once

Một tình huống quan trọng:

~~~text
Worker claim record
       |
       v
SMTP nhận email thành công
       |
       v
Worker bị kill trước khi UPDATE status = SUBMITTED
       |
       v
Lease hết hạn
       |
       v
Worker khác claim lại record
       |
       v
Email có thể được gửi lần thứ hai
~~~

Database không biết SMTP đã nhận email nếu worker chưa kịp ghi kết quả. SMTP và database không có transaction chung để commit hai thao tác cùng lúc.

Transactional outbox thường cung cấp mô hình **at-least-once attempt**: yêu cầu được lưu bền vững và có thể được thử lại, nhưng một side effect có thể xảy ra nhiều lần trong một số failure window.

### Giảm nguy cơ gửi trùng

- Dùng một outbox ID hoặc idempotency key ổn định cho cùng một event.
- Nếu provider API hỗ trợ idempotency key, gửi cùng key cho các lần retry của một yêu cầu.
- Lưu provider message ID khi có phản hồi.
- Tạo unique constraint cho business event để tránh insert outbox trùng.
- Theo dõi trạng thái attempt và thời điểm gửi.
- Thiết kế email có thể chịu được việc người nhận nhận trùng nếu không có idempotency từ provider.

SMTP chuẩn không cung cấp cơ chế idempotency thống nhất. Header Message-ID hữu ích cho correlation và chẩn đoán, nhưng không bảo đảm mọi SMTP provider hoặc mailbox sẽ loại bỏ message trùng. Không tuyên bố exactly-once chỉ vì database có cột status.

## 13. Phân loại lỗi và thiết kế retry

Không phải lỗi gửi mail nào cũng nên retry.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Tạm thời | Connection timeout, server unavailable, rate limit tạm thời | Retry với backoff và jitter |
| Cấu hình | Credential sai, host sai, TLS lỗi | Dừng retry dày đặc và cảnh báo vận hành |
| Nội dung | Recipient không hợp lệ, file vượt giới hạn, template lỗi | Đánh dấu FAILED để sửa dữ liệu |
| Policy | Sender/domain bị chặn, MIME type không được phép | Không retry nguyên message |
| Kết quả không rõ | Timeout sau khi SMTP DATA có thể đã được nhận | Đối soát provider hoặc chấp nhận rủi ro duplicate |

Một lịch retry đơn giản có thể tăng theo cấp số nhân:

~~~text
attempt 1: chờ 30 giây
attempt 2: chờ 1 phút
attempt 3: chờ 2 phút
attempt 4: chờ 4 phút
attempt 5: chờ 8 phút
...
~~~

Trong production nên thêm jitter để nhiều worker không đồng loạt retry tại cùng thời điểm, giới hạn thời gian chờ tối đa và giới hạn số lần thử. Các giá trị phải dựa trên SLA của provider và loại email.

Ví dụ tính delay:

~~~java
public Duration retryDelay(int attempt) {
    int exponent = Math.min(Math.max(attempt - 1, 0), 8);
    long baseSeconds = 30L * (1L << exponent);
    long cappedSeconds = Math.min(baseSeconds, 3600L);

    long jitterSeconds =
        ThreadLocalRandom.current().nextLong(0, 16);

    return Duration.ofSeconds(cappedSeconds + jitterSeconds);
}
~~~

Đây là policy minh họa. Với hệ thống lớn, nên dùng retry framework hoặc scheduler hiện có để tránh tự xây cơ chế phân tán phức tạp.

### Không retry vô hạn

Sau số lần thử tối đa, chuyển record sang FAILED hoặc DEAD_LETTER để có thể quan sát và xử lý thủ công. Lưu mã lỗi đã chuẩn hóa, số lần thử và correlation ID. Không lưu password, nội dung HTML hoặc dữ liệu nhạy cảm trong last_error.

Một thao tác requeue thủ công nên có audit log và lý do. Khi sửa lỗi cấu hình hoặc dữ liệu, người vận hành có thể đưa record về trạng thái có thể xử lý lại.

## 14. SMTP accepted không đồng nghĩa delivered

Khi JavaMailSender.send(...) trả về bình thường, adapter thường chỉ biết transport đã hoàn tất việc submission theo hợp đồng thư viện. Điều đó không chứng minh:

- Email đã vào Inbox.
- Email không bị bounce sau đó.
- Email không bị spam filter.
- Người nhận đã mở hoặc đọc email.

Nên đặt trạng thái outbox là SUBMITTED hoặc ACCEPTED_BY_TRANSPORT khi SMTP submission thành công. Nếu provider có webhook/event cho delivered, bounced, deferred hoặc complained, lưu các trạng thái đó trong một luồng theo dõi delivery riêng.

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- SMTP accepted ----> SUBMITTED
   |                            |
   |                            +--> DELIVERED (provider event)
   |                            +--> BOUNCED (provider event)
   |
   +---- transient error --> RETRY_WAIT
   |
   +---- permanent error --> FAILED
~~~

SMTP không phải lúc nào cũng cung cấp event giao thư cuối cùng. Nếu chỉ dùng SMTP relay cơ bản, trạng thái SUBMITTED có thể là mức quan sát cuối cùng mà ứng dụng có.

## 15. Payload outbox và template cần có version

Nếu worker chỉ lưu order ID rồi render email sau vài phút, dữ liệu đơn hàng có thể đã thay đổi. Email xác nhận có thể hiển thị địa chỉ, tổng tiền hoặc thông tin khác với thời điểm xác nhận.

Có hai lựa chọn:

**Snapshot payload:** lưu những giá trị cần thiết ngay khi transaction commit. Worker dùng snapshot đó để render nội dung nhất quán với event.

**Reference payload:** lưu aggregate ID và version. Worker đọc lại dữ liệu tương ứng với version đã phát sinh event. Cách này cần hệ thống có history/event version hoặc cơ chế đảm bảo đọc đúng snapshot.

Với email xác nhận giao dịch, snapshot thường dễ hiểu hơn vì nội dung cần khớp với sự kiện đã commit. Với template, nên ghi template key và version nếu email cần tái lập nội dung về sau. Nếu worker dùng template mới nhất sau deployment, một event cũ có thể được render bằng layout hoặc câu chữ khác.

Payload nên chứa đủ dữ liệu để xử lý ổn định nhưng không quá nhiều. Tránh lưu password, reset token hoặc dữ liệu cá nhân không cần thiết trong outbox lâu hơn thời gian vận hành cho phép.

## 16. Xử lý attachment trong outbox

Không nên lưu file PDF hoặc ảnh lớn dưới dạng Base64 trong cột payload JSON. Cách đó làm database phình to, tăng chi phí backup và khiến worker phải parse payload lớn.

Thay vào đó, lưu reference tới file đã được lưu bền vững:

~~~json
{
  "eventId": "9c85b7d0-1234-4abc-9abc-123456789012",
  "template": "invoice-email",
  "templateVersion": 3,
  "recipient": "customer@example.com",
  "attachment": {
    "fileId": "invoice-2026-001",
    "fileName": "invoice.pdf",
    "contentType": "application/pdf"
  }
}
~~~

Worker lấy file bằng storage port, kiểm tra quyền và trạng thái file, rồi stream nội dung vào MIME message. File phải còn tồn tại cho tới khi outbox record được xử lý hoặc hết retention. Nếu file bị xóa quá sớm, outbox sẽ tồn tại nhưng không còn đủ dữ liệu để gửi.

Với object storage, nên lưu version hoặc immutable key để nội dung file không thay đổi giữa lúc tạo outbox và lúc gửi.

## 17. Khi nào dùng event listener, khi nào dùng outbox?

| Nhu cầu | @TransactionalEventListener(AFTER_COMMIT) | Transactional outbox |
| --- | --- | --- |
| Chỉ chạy sau khi DB commit | Có | Có, worker chỉ đọc record đã commit |
| Tránh gửi khi transaction rollback | Có | Có |
| Yêu cầu gửi tồn tại sau process crash | Không tự bảo đảm | Có, record nằm trong database |
| Retry sau khi SMTP lỗi | Cần tự xây thêm cơ chế bền vững | Có thể triển khai qua worker và trạng thái |
| Nhiều worker xử lý song song | Không phải mục tiêu chính | Có thể claim bằng lock/lease |
| Độ phức tạp vận hành | Thấp | Cao hơn, cần bảng, worker và cleanup |
| Phù hợp | Side effect best-effort | Email giao dịch quan trọng cần theo dõi và retry |

Có thể kết hợp cả hai: outbox row được tạo trong transaction, sau commit phát một tín hiệu đánh thức worker để giảm độ trễ. Tín hiệu chỉ là tối ưu; worker vẫn phải poll hoặc có cơ chế khôi phục để không phụ thuộc vào event trong bộ nhớ.

Không nên dùng event listener làm nơi lưu outbox sau commit. Nếu listener crash trước khi insert outbox, yêu cầu gửi vẫn bị mất. Insert outbox phải nằm trong transaction nghiệp vụ ban đầu.

## 18. Transactional outbox với CDC hoặc polling

Có hai cách phổ biến để phát hiện outbox record mới:

### Polling

Worker định kỳ truy vấn các record PENDING/RETRY_WAIT đến hạn. Ưu điểm là dễ triển khai và không cần nền tảng streaming riêng. Nhược điểm là có độ trễ theo chu kỳ polling và cần tối ưu query/index, lock và cleanup.

Polling phù hợp với nhiều ứng dụng Spring Boot vừa và nhỏ. Batch size, số worker và chu kỳ polling nên được cấu hình theo tốc độ phát sinh email và khả năng SMTP provider.

### Change Data Capture (CDC)

Một công cụ CDC đọc transaction log của database và phát các thay đổi outbox tới message broker. Worker tiêu thụ event từ broker rồi gửi email.

Ưu điểm:

- Phát hiện thay đổi gần real-time.
- Giảm truy vấn polling liên tục.
- Có thể tích hợp vào event-driven architecture sẵn có.

Nhược điểm:

- Hạ tầng và vận hành phức tạp hơn.
- Cần quản lý offset, replay và duplicate.
- Consumer vẫn phải idempotent.
- Phải bảo đảm outbox event được xử lý và retention phù hợp.

CDC không làm cho SMTP trở thành exactly-once. Nó thay đổi cách chuyển outbox record tới worker; failure window giữa SMTP accepted và cập nhật trạng thái vẫn còn.

## 19. Kiểm thử failure window

Để kiểm tra chiến lược transaction và outbox, nên mô phỏng các tình huống cụ thể:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Business transaction rollback trước commit | Không có outbox row được commit; worker không gửi |
| Business transaction commit thành công | Outbox row tồn tại và worker có thể claim |
| SMTP tạm lỗi | Record được lên lịch RETRY_WAIT |
| SMTP lỗi vĩnh viễn | Record chuyển FAILED hoặc dead-letter |
| Worker crash sau claim nhưng trước send | Lease hết hạn và worker khác có thể claim lại |
| Worker crash sau SMTP accepted nhưng trước update status | Có nguy cơ gửi trùng; hệ thống phải có chiến lược idempotency/đối soát |
| Hai worker chạy cùng lúc | Một record không bị claim đồng thời nhờ locking/lease |
| Template hoặc file reference không còn hợp lệ | Lỗi được phân loại và ghi nhận, không retry vô hạn |
| Provider trả webhook bounce | Trạng thái delivery được cập nhật theo provider event |

### Unit test transaction cùng outbox

Có thể kiểm tra use case tạo record cùng transaction bằng test database:

~~~java
@Test
void rollbackDoesNotLeaveOutboxMessage() {
    assertThrows(RuntimeException.class, () ->
        transactionTemplate.executeWithoutResult(status -> {
            orderService.confirm(orderId);
            throw new RuntimeException("force rollback");
        })
    );

    assertEquals(
        0,
        outboxRepository.countByAggregateId(orderId.toString())
    );
}
~~~

Test cần dùng cùng transaction manager và database cho order repository và outbox repository. Nếu test gọi service qua Spring proxy, transaction annotation sẽ được áp dụng đúng; tránh gọi trực tiếp method nội bộ của cùng instance rồi kỳ vọng proxy hoạt động.

### Test worker bằng fake mail adapter

~~~java
class FakeMailDeliveryPort implements MailDeliveryPort {

    private int attempts;
    private boolean fail;

    @Override
    public void send(OutgoingMail mail) {
        attempts++;

        if (fail) {
            throw new TransientMailException("SMTP unavailable");
        }
    }

    int attempts() {
        return attempts;
    }
}
~~~

Dùng fake để kiểm tra worker cập nhật SUBMITTED khi gửi thành công và RETRY_WAIT khi lỗi tạm thời. Integration test riêng có thể dùng SMTP test server để kiểm tra MIME thực tế. Không cần dùng SMTP production trong test.

## 20. Quan sát và vận hành outbox

Outbox là một hàng đợi bền vững nằm trong database, vì vậy cần theo dõi sức khỏe của nó:

- Số record PENDING.
- Số record PROCESSING và tuổi của lease.
- Số record RETRY_WAIT.
- Số record FAILED/dead-letter.
- Tuổi của record PENDING lâu nhất.
- Số lần thử trung bình và p95.
- Thời gian từ created_at tới submitted_at.
- SMTP error rate theo provider.
- Tỷ lệ duplicate hoặc kết quả gửi không rõ nếu có thể quan sát.

Một số cảnh báo hữu ích:

- PENDING lâu hơn SLA.
- PROCESSING có lease hết hạn tăng bất thường.
- RETRY_WAIT tăng liên tục.
- FAILED vượt ngưỡng.
- Không có record nào được xử lý trong khi traffic vẫn phát sinh.
- Provider liên tục từ chối kết nối hoặc rate limit.

### Cleanup và retention

Không nên giữ outbox row vô thời hạn nếu không có nhu cầu audit. Có thể archive hoặc xóa record đã hoàn tất sau khoảng thời gian theo chính sách vận hành. Trước khi cleanup, cần bảo đảm provider event/bounce reconciliation đã hoàn thành nếu hệ thống cần trạng thái delivery.

Payload có thể chứa email, tên khách hàng, địa chỉ hoặc dữ liệu đơn hàng. Áp dụng quyền truy cập database, retention, masking log và quy trình xóa dữ liệu phù hợp.

## 21. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gửi SMTP trước commit | Email có thể thông báo cho giao dịch rollback | Chuyển sang xử lý sau commit hoặc outbox |
| Gửi sau commit bằng lời gọi tuần tự trong controller | Process crash giữa commit và send làm mất yêu cầu | Lưu outbox trong transaction |
| Cho rằng AFTER_COMMIT bảo đảm không mất event | Event mặc định chỉ ở bộ nhớ | Dùng outbox cho yêu cầu bền vững |
| Dùng @Async để thay thế outbox | Executor không phải durable queue | Dùng worker/outbox hoặc broker bền vững |
| Insert outbox bằng REQUIRES_NEW | Outbox có thể commit dù nghiệp vụ rollback | Dùng cùng transaction database |
| Giữ DB transaction trong lúc gửi SMTP | Giữ connection/lock khi chờ network | Claim record rồi commit trước khi gửi |
| Đánh dấu SUBMITTED trước khi gọi SMTP | Worker crash làm mất yêu cầu gửi | Chỉ cập nhật sau kết quả gửi |
| Giả định retry luôn an toàn | Có thể gửi trùng sau timeout mơ hồ | Idempotency và reconciliation |
| Gọi SMTP accepted là delivered | Báo cáo trạng thái người nhận sai | Tách submission khỏi delivery event |
| Retry vô hạn | Queue phình và lặp lỗi vĩnh viễn | Backoff, max attempts và dead-letter |
| Lưu attachment lớn trong JSON payload | Database và backup phình to | Lưu file reference bất biến |
| Chỉ poll PENDING, bỏ PROCESSING hết lease | Record bị kẹt khi worker chết | Lease expiration và reclaim |
| Xóa outbox ngay sau submission | Mất khả năng điều tra/reconcile | Retention và archive có kiểm soát |

## 22. Chọn chiến lược theo mức độ quan trọng của email

Không phải email nào cũng cần outbox. Có thể quyết định theo hậu quả nếu thông báo bị mất hoặc gửi trùng.

| Loại thông báo | Chiến lược thường phù hợp | Lý do |
| --- | --- | --- |
| Email debug/dev | Local capture hoặc log | Không phải thông báo giao dịch |
| Email báo cáo không quan trọng | AFTER_COMMIT hoặc job định kỳ | Có thể tái tạo hoặc chấp nhận mất |
| Email xác nhận đơn hàng | Transactional outbox | Người dùng cần biết giao dịch đã được ghi nhận |
| Email hóa đơn/chứng từ | Outbox + file reference bất biến | Cần đối chiếu nội dung và retry |
| Newsletter | Queue/campaign system riêng | Có batch, rate limit và unsubscribe policy |

Đối với email bảo mật như reset password, retry phải kiểm tra thời hạn token và trạng thái tài khoản. Không gửi lại token đã hết hạn hoặc token đã bị thu hồi. Outbox giúp lưu yêu cầu, nhưng logic nghiệp vụ vẫn phải xác nhận nội dung còn hợp lệ tại thời điểm worker xử lý.

## 23. Quy trình triển khai trong ứng dụng Spring

Một lộ trình thực tế:

1. **Xác định mức độ quan trọng của email** và hậu quả khi email mất hoặc gửi trùng.
2. **Tìm vị trí gọi JavaMailSender** bên trong transaction hiện tại.
3. **Tách port gửi mail** khỏi use case để có thể thay adapter và fake trong test.
4. **Với email best-effort**, cân nhắc @TransactionalEventListener(AFTER_COMMIT) và xử lý exception rõ ràng.
5. **Với email cần độ tin cậy**, tạo outbox table và ghi record trong cùng transaction với thay đổi nghiệp vụ.
6. **Xây worker** claim record bằng transaction ngắn, gửi ngoài transaction và cập nhật kết quả bằng transaction mới.
7. **Thêm lease, retry, backoff, max attempts và dead-letter**.
8. **Dùng idempotency key** ổn định và xác định cách xử lý kết quả SMTP không rõ.
9. **Theo dõi SUBMITTED và provider delivery events** nếu cần biết trạng thái cuối.
10. **Kiểm thử rollback, process crash, SMTP failure, duplicate và concurrency** trên môi trường phù hợp.

Sơ đồ tổng thể:

~~~text
Business request
      |
      v
BEGIN DATABASE TRANSACTION
      |
      +--> Update business aggregate
      |
      +--> Insert mail_outbox row
      |
      v
COMMIT
      |
      v
Outbox worker claims row
      |
      v
Commit claim / lease
      |
      v
Build email + call MailDeliveryPort
      |
      +---- success ----> Mark SUBMITTED
      |
      +---- transient --> Schedule RETRY_WAIT
      |
      +---- permanent --> Mark FAILED
      |
      v
Provider events (if available)
      |
      +--> DELIVERED / BOUNCED / DEFERRED
~~~

Điểm cốt lõi là transaction database chỉ ghi nhận trạng thái nghiệp vụ và ý định gửi. Worker thực hiện side effect sau khi dữ liệu đã commit.

## 24. Ghi nhớ

Khi transaction commit nhưng gửi mail thất bại, ứng dụng đang phối hợp hai hệ thống không có transaction chung:

- Gửi SMTP trước commit có thể tạo email cho một thay đổi sau đó rollback.
- Gửi sau commit tránh thông báo trước khi dữ liệu được xác nhận, nhưng process crash có thể làm mất lời gọi gửi.
- **@TransactionalEventListener(AFTER_COMMIT)** phù hợp với side effect best-effort; event trong bộ nhớ không bảo đảm tồn tại sau process crash.
- **@Async** chỉ chạy việc trên executor; nó không thay thế một hàng đợi bền vững.
- Transactional outbox ghi yêu cầu gửi cùng transaction với thay đổi nghiệp vụ để worker có thể tiếp tục sau khi ứng dụng khởi động lại.
- Outbox row và dữ liệu nghiệp vụ phải dùng cùng database transaction manager; tránh **REQUIRES_NEW** cho thao tác insert outbox.
- Worker claim bằng transaction ngắn, gửi ngoài transaction và cập nhật trạng thái bằng transaction mới.
- Lease giúp thu hồi record khi worker chết, nhưng vẫn có failure window gây gửi trùng.
- Outbox thường cung cấp at-least-once processing; SMTP không có idempotency chung để bảo đảm exactly-once.
- Dùng idempotency key nếu provider hỗ trợ, lưu attempt và đối soát kết quả khi SMTP timeout không rõ.
- Phân loại lỗi transient/permanent, dùng backoff có jitter, giới hạn attempts và dead-letter.
- SMTP accepted chỉ xác nhận submission theo transport; delivered cần provider event hoặc tín hiệu giao thư đáng tin cậy.
- Lưu payload vừa đủ, cân nhắc snapshot/version, file reference bất biến, quyền truy cập và retention.
- Theo dõi tuổi outbox, retry, lỗi provider và record bị kẹt để vận hành chủ động.

Với email giao dịch quan trọng, transactional outbox là cách thực tế để giữ yêu cầu gửi đồng bộ với thay đổi database và tiếp tục xử lý sau lỗi tiến trình hoặc SMTP. Nó không loại bỏ mọi khả năng gửi trùng, nhưng tạo ra một record bền vững, có trạng thái và có thể retry/đối soát thay vì để thông báo phụ thuộc vào một lời gọi mạng ngay sau transaction commit.
