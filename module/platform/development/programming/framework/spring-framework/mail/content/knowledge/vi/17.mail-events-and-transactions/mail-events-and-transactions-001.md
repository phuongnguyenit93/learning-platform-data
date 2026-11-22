# Gửi email trực tiếp trong transaction nghiệp vụ

Trong một ứng dụng Spring, thao tác như xác nhận đơn hàng, thanh toán hóa đơn hoặc tạo tài khoản thường chạy bên trong **database transaction**. Ứng dụng cập nhật dữ liệu, sau đó có thể cần gửi email thông báo cho người dùng.

Một cách làm dễ viết là gọi `JavaMailSender.send(...)` ngay trong method có `@Transactional`. Tuy nhiên, gửi email qua SMTP là một **tác động bên ngoài database**. Transaction manager của Spring có thể commit hoặc rollback dữ liệu trong database, nhưng không thể thu hồi một email mà SMTP server đã nhận.

Vì vậy, cần hiểu rõ thời điểm gửi và ý nghĩa của kết quả:

- Nếu gửi email **trước khi database commit**, người nhận có thể nhận thông báo cho một giao dịch sau đó bị rollback.
- Nếu đợi **sau khi commit** rồi mới gửi, dữ liệu đã được lưu nhưng tiến trình có thể dừng trước khi gửi email.
- Nếu dùng **transactional outbox**, dữ liệu nghiệp vụ và yêu cầu gửi email được ghi trong cùng database transaction; một worker gửi email sau đó và có thể retry.

Bài học này giải thích cách gửi trực tiếp trong transaction, các rủi ro của cách làm đó, cách dùng sự kiện sau commit và khi nào nên dùng outbox.

## 1. Database transaction và SMTP là hai hệ thống độc lập

Giả sử người dùng xác nhận đơn hàng. Ứng dụng cần:

1. Chuyển trạng thái đơn hàng sang `CONFIRMED`.
2. Lưu thời điểm xác nhận.
3. Gửi email xác nhận cho khách hàng.

Database transaction có thể bảo đảm các thao tác SQL liên quan được commit hoặc rollback cùng nhau. SMTP server là một hệ thống bên ngoài, không tham gia transaction đó.

~~~mermaid
sequenceDiagram
    participant A as Application Service
    participant D as Database
    participant S as SMTP Server
    A->>D: BEGIN
    A->>D: UPDATE order = CONFIRMED
    A->>S: SMTP send confirmation
    S-->>A: Accepted
    A->>D: COMMIT
~~~

Nếu commit thành công, ví dụ có vẻ hoạt động đúng. Nhưng nếu bước commit thất bại sau khi SMTP đã chấp nhận thư, email đã đi ra ngoài trong khi dữ liệu đơn hàng không được lưu.

Điều này xảy ra vì:

- **Database rollback** chỉ hoàn tác những thay đổi được quản lý bởi transaction manager/database.
- **SMTP submission** không nằm trong transaction database.
- Email đã được server bên ngoài tiếp nhận không thể được thu hồi bằng `ROLLBACK`.

Không nên xem lời gọi SMTP như một câu SQL khác trong cùng transaction. Hai thao tác có ranh giới và cơ chế xác nhận riêng.

## 2. Gọi send trực tiếp trong method @Transactional

Một ví dụ thường gặp:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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

    @Transactional
    public void confirmOrder(Long orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();
        orderRepository.save(order);

        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("orders@example.com");
        mail.setTo(order.getCustomerEmail());
        mail.setSubject(
                "Đơn hàng " + order.getOrderNumber() + " đã được xác nhận");
        mail.setText(
                "Đơn hàng " + order.getOrderNumber()
                + " của bạn đã được xác nhận.");

        mailSender.send(mail);
    }
}
~~~

Đoạn code này dễ hiểu và có thể phù hợp với một demo nhỏ. Nhưng vì `confirmOrder(...)` đang chạy trong transaction, `mailSender.send(mail)` được gọi **trước thời điểm transaction commit**. Spring thường commit transaction khi method được gọi qua transaction proxy kết thúc bình thường.

Nếu gửi mail thành công nhưng một thao tác database hoặc quá trình commit sau đó thất bại, khách hàng vẫn có thể nhận email xác nhận cho đơn hàng chưa được xác nhận trong database.

### 2.1. Kịch bản gửi thành công nhưng database rollback

~~~text
T1  BEGIN database transaction
T2  UPDATE order SET status = 'CONFIRMED'
T3  SMTP nhận email và trả kết quả chấp nhận
T4  Một constraint/commit operation thất bại
T5  Database ROLLBACK

Kết quả:
  Database: order chưa được xác nhận
  Email: khách hàng đã nhận thông báo xác nhận
~~~

Đây là một trạng thái không nhất quán giữa database và thông báo bên ngoài. Khi khách hàng bấm vào liên kết hoặc gọi hỗ trợ, ứng dụng có thể không tìm thấy trạng thái như email đã nói.

### 2.2. Kịch bản gửi thất bại

Nếu `mailSender.send(mail)` ném `MailException` và exception thoát khỏi method `@Transactional`, Spring mặc định rollback transaction đối với runtime exception và `Error` (trừ khi có cấu hình rollback rule khác).

Điều này có thể tạo hành vi:

~~~text
T1  BEGIN
T2  UPDATE order = CONFIRMED
T3  SMTP báo lỗi
T4  MailException thoát khỏi method
T5  Database ROLLBACK
~~~

Đôi khi ứng dụng muốn hành vi này, nhưng cần hiểu ý nghĩa: **lỗi email đang làm thất bại cả nghiệp vụ xác nhận đơn hàng**. Đây là một quyết định nghiệp vụ mạnh, không nên vô tình có được chỉ vì gọi sender trong transaction.

Nếu code bắt exception và chỉ ghi log:

~~~java
try {
    mailSender.send(mail);
} catch (MailException ex) {
    log.warn("Could not send confirmation", ex);
}
~~~

thì method có thể tiếp tục và transaction commit. Đơn hàng được xác nhận nhưng email thất bại. Đây có thể là lựa chọn hợp lý nếu email là tác vụ phụ, nhưng lúc đó hệ thống phải có cách ghi nhận và xử lý lại lỗi nếu email quan trọng.

### 2.3. Kết quả SMTP có thể không xác định

Một tình huống khó hơn:

1. Ứng dụng truyền message tới SMTP server.
2. SMTP server chấp nhận thư.
3. Kết nối bị ngắt trước khi client nhận phản hồi cuối cùng.

Ứng dụng có thể nhận timeout hoặc exception dù server đã tiếp nhận thư. Nếu exception làm database rollback rồi ứng dụng retry, người nhận có thể nhận thư trùng.

Vì vậy, lỗi transport không phải lúc nào cũng có nghĩa “server chắc chắn chưa nhận email”. Hệ thống gửi mail cần phân biệt lỗi chắc chắn thất bại và kết quả không xác định khi thiết kế retry.

## 3. Gửi email trong transaction còn kéo dài thời gian giữ transaction

SMTP có độ trễ mạng và phụ thuộc hệ thống bên ngoài. Khi gọi sender trực tiếp bên trong transaction:

- transaction phải chờ kết nối và phản hồi SMTP;
- database connection có thể bị giữ lâu hơn;
- row lock hoặc các tài nguyên transaction có thể tồn tại lâu hơn;
- throughput giảm khi SMTP chậm;
- timeout SMTP có thể làm request nghiệp vụ kéo dài hoặc thất bại.

Ví dụ, cập nhật một đơn hàng thường mất vài chục mili giây, nhưng gửi SMTP có thể mất vài giây khi server chậm. Nếu có nhiều request cùng lúc, transaction kéo dài có thể làm tăng số connection đang sử dụng và tranh chấp khóa.

~~~text
Transaction duration

Chỉ cập nhật database:
| DB work |

Gửi SMTP trong transaction:
| DB work |--------- SMTP wait ---------|

                         ^ connection/lock có thể vẫn bị giữ
~~~

Đây là một lý do thực tế để tách gửi mail khỏi transaction nghiệp vụ, kể cả khi không xét đến lỗi rollback.

## 4. Khi nào gửi trực tiếp trong transaction có thể chấp nhận?

Không phải mọi email đều cần outbox. Một thao tác gửi trực tiếp có thể chấp nhận khi:

- ứng dụng nhỏ hoặc demo;
- email chỉ là thông báo phụ, mất một lần gửi không gây hậu quả đáng kể;
- nghiệp vụ chấp nhận email có thể được gửi trước khi commit;
- transaction ngắn và việc SMTP chậm không ảnh hưởng đáng kể;
- có quy trình hỗ trợ để xử lý thủ công khi thông báo thất bại.

Ví dụ một công cụ nội bộ gửi email nhắc nhở không quan trọng có thể chấp nhận việc gửi trực tiếp sau khi thao tác dữ liệu đơn giản hoàn tất.

Ngược lại, với xác nhận thanh toán, hóa đơn, đặt vé, tạo tài khoản hoặc email chứa mã xác thực, cần xác định rõ tính nhất quán và khả năng khôi phục. Những trường hợp này thường nên dùng ít nhất cơ chế sau commit; nếu không được phép mất thông báo thì nên cân nhắc outbox.

## 5. Dùng sự kiện để gửi email sau khi transaction commit

Một cách đơn giản trong Spring là **phát application event trong transaction**, rồi lắng nghe bằng `@TransactionalEventListener` với phase `AFTER_COMMIT`.

~~~mermaid
sequenceDiagram
    participant A as OrderService
    participant D as Database
    participant E as Spring Event
    participant L as Mail Listener
    participant S as SMTP
    A->>D: BEGIN
    A->>D: Update order
    A->>E: publish OrderConfirmedEvent
    Note over E,L: Listener chờ transaction hoàn tất
    A->>D: COMMIT
    D-->>A: Commit success
    E->>L: AFTER_COMMIT event
    L->>S: Send confirmation
    S-->>L: Submission result
~~~

Listener chỉ chạy sau khi transaction đã commit thành công. Nếu transaction rollback, listener ở phase `AFTER_COMMIT` không được gọi.

### 5.1. Tạo event bất biến

Event nên chứa dữ liệu đủ để xử lý thông báo và có snapshot ổn định:

~~~java
package com.example.order.event;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderConfirmedEvent(
        Long orderId,
        String orderNumber,
        String customerEmail,
        String customerName,
        BigDecimal total,
        Instant confirmedAt) {
}
~~~

Không nhất thiết truyền toàn bộ `OrderEntity` vào event. Nếu listener chạy sau commit hoặc bất đồng bộ, entity có thể đã detached, lazy relationship không còn truy cập được, hoặc dữ liệu đã thay đổi trước khi listener đọc. Một event chứa những giá trị đã chụp giúp thông báo phản ánh đúng sự kiện đã xảy ra.

Nếu event có collection hoặc object mutable, cần defensive copy như `List.copyOf` và dùng các kiểu dữ liệu bất biến phù hợp.

### 5.2. Publish event bên trong transaction

~~~java
import java.time.Instant;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public OrderApplicationService(
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

        eventPublisher.publishEvent(
                new OrderConfirmedEvent(
                        order.getId(),
                        order.getOrderNumber(),
                        order.getCustomerEmail(),
                        order.getCustomerName(),
                        order.getTotal(),
                        Instant.now()
                )
        );
    }
}
~~~

Event được publish trong lúc transaction còn hoạt động. Việc publish chỉ thông báo cho Spring event infrastructure; listener gắn với `AFTER_COMMIT` sẽ được gọi sau khi commit thành công.

### 5.3. Lắng nghe sau commit và gửi email

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderMailListener {
    private final JavaMailSender mailSender;

    public OrderMailListener(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("orders@example.com");
        mail.setTo(event.customerEmail());
        mail.setSubject(
                "Đơn hàng " + event.orderNumber() + " đã được xác nhận");
        mail.setText("""
                Xin chào %s,

                Đơn hàng %s đã được xác nhận.
                Tổng cộng: %s
                """.formatted(
                event.customerName(),
                event.orderNumber(),
                event.total()
        ));

        mailSender.send(mail);
    }
}
~~~

Đây là ví dụ plain text. Nếu cần HTML, listener có thể gọi một application-level `MailService` để render/gửi theo contract của ứng dụng.

**Điểm quan trọng:** listener chỉ được gọi khi transaction commit. Nếu cập nhật đơn hàng bị rollback, email không được gửi.

### 5.4. Hành vi mặc định khi không có transaction

`@TransactionalEventListener` mặc định yêu cầu có transaction gắn với event. Nếu event được publish ngoài transaction, listener không chạy. Thuộc tính `fallbackExecution` có thể thay đổi hành vi này:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void onOrderConfirmed(OrderConfirmedEvent event) {
    // ...
}
~~~

Chỉ bật `fallbackExecution = true` khi nghiệp vụ thực sự muốn listener chạy cả lúc không có transaction. Nếu không, cấu hình mặc định giúp phát hiện việc event được publish ngoài transaction thay vì âm thầm gửi theo một ngữ nghĩa khác.

## 6. AFTER_COMMIT giải quyết được gì và còn thiếu gì?

`AFTER_COMMIT` giải quyết một vấn đề quan trọng: **không gửi email cho giao dịch đã rollback**.

Nhưng event trong bộ nhớ của ứng dụng không phải một hàng đợi bền vững. Có một khoảng thời gian giữa database commit và listener thực hiện xong việc gửi:

~~~text
T1  Database COMMIT thành công
T2  Process bị kill hoặc JVM crash
T3  Listener chưa kịp gọi SMTP

Kết quả:
  Database: giao dịch đã lưu
  Email: chưa được gửi
~~~

Không có transaction database nào có thể khôi phục event trong bộ nhớ sau khi process đã dừng. Do đó:

- `AFTER_COMMIT` phù hợp với thông báo đơn giản, nơi có thể chấp nhận rủi ro mất event trong khoảng thời gian này.
- Nếu phải bảo đảm yêu cầu gửi được lưu cùng giao dịch nghiệp vụ, hãy dùng transactional outbox.

### 6.1. Listener đồng bộ vẫn làm caller chờ

`@TransactionalEventListener` mặc định được gọi đồng bộ trong quá trình hoàn tất transaction. Vì vậy, dù listener chạy **sau commit**, thread hoàn tất transaction có thể vẫn phải chờ SMTP gửi xong trước khi request trả về.

Điều này có nghĩa:

- database đã commit trước khi gửi;
- request vẫn có thể chờ thao tác gửi;
- lỗi gửi có thể xuất hiện sau khi dữ liệu đã commit.

Nếu method listener ném exception, exception có thể truyền về thread thực hiện commit/caller tùy đường gọi và cấu hình. Nhưng **database đã commit và không thể rollback chỉ vì listener gửi mail thất bại**. API có thể gặp tình huống caller nhận lỗi dù thay đổi nghiệp vụ đã được lưu; cần xử lý điều này có chủ đích.

Một cách là bắt lỗi, ghi nhận trạng thái gửi thất bại và chuyển cho quy trình retry/ops. Tuy nhiên, chỉ log lỗi rồi bỏ qua có thể làm mất thông báo nếu process dừng; outbox phù hợp hơn khi yêu cầu tin cậy cao.

### 6.2. Có thể kết hợp @Async

Có thể yêu cầu listener chạy qua executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.transaction.event.TransactionalEventListener;

@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderConfirmed(OrderConfirmedEvent event) {
    // Gửi email trong executor thread.
}
~~~

Ứng dụng cần bật async execution bằng cấu hình phù hợp, ví dụ `@EnableAsync`. Cách này giúp thread xử lý transaction không phải đợi SMTP trong listener.

Nhưng `@Async` chỉ chuyển công việc sang executor trong process:

- task có thể mất nếu process dừng;
- executor có giới hạn queue/thread và có thể từ chối task;
- exception không được caller bắt theo cách đồng bộ thông thường;
- không tự có retry bền vững hoặc trạng thái job.

Vì vậy, `@Async + AFTER_COMMIT` là cách giảm thời gian chờ, **không phải cơ chế đảm bảo gửi mail bền vững**.

## 7. Dùng TransactionSynchronization khi cần callback sau commit

Spring cũng cung cấp `TransactionSynchronizationManager` để đăng ký callback:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    mailService.send(outgoingMail);
                }
            }
    );
} else {
    // Xác định rõ hành vi khi không có transaction.
    mailService.send(outgoingMail);
}
~~~

Callback `afterCommit()` chạy sau khi transaction commit. Cách này hữu ích cho một số tích hợp hạ tầng, nhưng thường `@TransactionalEventListener` diễn đạt ý định nghiệp vụ rõ hơn và dễ tách listener thành bean.

Nếu dùng callback thủ công:

- phải quyết định hành vi khi không có transaction;
- tránh giữ entity hoặc resource chỉ còn hợp lệ trong transaction;
- truyền dữ liệu snapshot;
- xử lý exception sau commit vì rollback không còn khả dụng;
- hiểu rõ callback không được lưu bền vững qua restart.

Không nên tạo một callback riêng cho mọi use case nếu application event đã đáp ứng được nhu cầu.

## 8. Transactional Outbox: lưu yêu cầu gửi cùng transaction

Nếu email là phần quan trọng của quy trình nghiệp vụ và không được mất khi process dừng, có thể dùng **Transactional Outbox Pattern**.

Ý tưởng:

1. Trong cùng database transaction, cập nhật dữ liệu nghiệp vụ.
2. Trong cùng transaction đó, insert một bản ghi outbox mô tả yêu cầu gửi email.
3. Commit một lần để cả dữ liệu nghiệp vụ và outbox cùng thành công hoặc cùng rollback.
4. Một worker/relay đọc outbox sau commit và gửi email.
5. Worker cập nhật trạng thái, retry hoặc đưa job vào dead-letter khi cần.

~~~mermaid
flowchart TD
    A["OrderApplicationService"] --> B["BEGIN DB transaction"]
    B --> C["Update order"]
    B --> D["Insert email outbox row"]
    C --> E{"COMMIT"}
    D --> E
    E -->|Success| F["Outbox relay"]
    E -->|Rollback| G["Order và outbox cùng rollback"]
    F --> H["Create MIME + send"]
    H --> I{"Submission result"}
    I -->|Success| J["Mark SUBMITTED"]
    I -->|Temporary failure| K["Schedule retry"]
    I -->|Permanent failure| L["Dead-letter / alert"]
~~~

### 8.1. Vì sao outbox tốt hơn event trong bộ nhớ?

`ApplicationEventPublisher` chỉ phát event trong process. Outbox lưu yêu cầu gửi trong database, cùng transaction với dữ liệu nghiệp vụ.

Ví dụ:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE id = 123;

INSERT INTO mail_outbox (
    id,
    event_type,
    recipient,
    template_id,
    payload,
    status,
    created_at
)
VALUES (
    'job-123',
    'ORDER_CONFIRMED',
    'alice@example.net',
    'order-confirmation',
    '{"orderNumber":"A123","totalText":"220.000 ₫"}',
    'PENDING',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Nếu transaction rollback, cả update đơn hàng và insert outbox đều bị rollback. Nếu commit thành công rồi process dừng, bản ghi outbox vẫn còn để worker xử lý sau khi ứng dụng khởi động lại.

### 8.2. Bảng outbox có thể chứa những trường nào?

Một schema minh họa:

~~~sql
CREATE TABLE mail_outbox (
    id               VARCHAR(64) PRIMARY KEY,
    event_type       VARCHAR(100) NOT NULL,
    recipient        VARCHAR(320) NOT NULL,
    template_id      VARCHAR(150) NOT NULL,
    template_version VARCHAR(50),
    payload          TEXT NOT NULL,
    status           VARCHAR(30) NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  TIMESTAMP,
    created_at       TIMESTAMP NOT NULL,
    submitted_at     TIMESTAMP,
    last_error_code  VARCHAR(100),
    last_error_at    TIMESTAMP
);
~~~

Đây là schema tham khảo; kiểu dữ liệu, index, JSON type, timestamp timezone và độ dài cần điều chỉnh theo database. Có thể bổ sung `locked_until`, `locked_by`, `lease_token` hoặc `version` để phối hợp nhiều worker.

Các trường chính:

- `id`: ID ổn định của job, phục vụ truy vết và deduplication.
- `event_type`: loại sự kiện nghiệp vụ.
- `recipient`: địa chỉ nhận đã được xác định.
- `template_id` và `template_version`: mẫu nội dung cần render.
- `payload`: snapshot dữ liệu trình bày.
- `status`: trạng thái xử lý.
- `attempts` và `next_attempt_at`: kiểm soát retry.
- `submitted_at`: thời điểm transport hoàn tất thao tác nộp thư.
- `last_error_code`: nguyên nhân thất bại đã được phân loại, tránh lưu toàn bộ nội dung nhạy cảm.

Không đưa SMTP password, OAuth token hoặc secret vào payload. Bảo vệ recipient và nội dung email theo chính sách lưu trữ dữ liệu cá nhân.

### 8.3. Ghi outbox trong cùng transaction

Một service có thể làm:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow();

        order.confirm();

        OrderConfirmationPayload payload =
                OrderConfirmationPayload.from(order);

        outbox.insert(
                MailOutboxMessage.pending(
                        "order-confirmed-" + order.getId(),
                        order.getCustomerEmail(),
                        "order-confirmation",
                        payload
                )
        );
    }
}
~~~

`orders.save(...)` có thể không cần nếu entity được quản lý bởi persistence context và dirty checking sẽ lưu thay đổi khi commit. Cách cụ thể phụ thuộc repository/JPA mapping.

Điểm quyết định là `outbox.insert(...)` tham gia **cùng transaction manager và cùng database transaction** với cập nhật đơn hàng. Nếu outbox được ghi sang một database khác hoặc một broker độc lập mà không có cơ chế phối hợp, tính nguyên tử này không còn tự động đúng.

### 8.4. Worker xử lý outbox

Worker thực hiện:

1. Claim một hoặc nhiều bản ghi `PENDING` đã tới thời điểm xử lý.
2. Lưu lease/lock hoặc đổi trạng thái để worker khác không xử lý cùng lúc.
3. Commit transaction claim ngắn.
4. Đọc payload và render nội dung.
5. Gọi MailService/JavaMailSender bên ngoài transaction claim.
6. Nếu sender trả về bình thường, cập nhật `SUBMITTED`.
7. Nếu lỗi tạm thời, tăng attempts và đặt `next_attempt_at`.
8. Nếu lỗi vĩnh viễn hoặc hết giới hạn retry, chuyển `FAILED_FINAL`/dead-letter.

Không nên giữ một database transaction và row lock mở trong suốt thời gian chờ SMTP. Việc claim nên ngắn; gửi là thao tác mạng bên ngoài; cập nhật kết quả nằm trong transaction riêng.

### 8.5. Trạng thái outbox

~~~text
PENDING
   |
   v
PROCESSING
   |--------------------------|
   v                          v
SUBMITTED                  RETRY_WAIT
                              |
                              v
                          PROCESSING
                              |
                              v
                         FAILED_FINAL
~~~

Tên trạng thái có thể khác nhau, nhưng cần phân biệt:

- job chưa được worker nhận;
- job đang được xử lý/đang có lease;
- transport đã nộp thư;
- job chờ retry;
- job kết thúc thất bại và cần can thiệp.

`SUBMITTED` vẫn không có nghĩa email đã đến Inbox. Delivery/bounce nếu cần phải được cập nhật từ provider event riêng.

## 9. Outbox vẫn cần xử lý gửi trùng

Outbox giúp không mất **yêu cầu gửi** khi transaction nghiệp vụ commit. Nó không tự bảo đảm SMTP gửi đúng một lần.

Kịch bản:

~~~text
T1 Worker lấy job J-123
T2 SMTP server chấp nhận email
T3 Worker bị crash trước khi cập nhật status = SUBMITTED
T4 Lease hết hạn
T5 Worker khác lấy lại J-123
T6 Email có thể được gửi lần thứ hai
~~~

Đây là đặc điểm thường gặp của hệ thống xử lý **at-least-once**. Để giảm rủi ro:

- dùng ID job ổn định và unique constraint cho sự kiện nghiệp vụ;
- nếu provider hỗ trợ idempotency key, gửi key theo contract của provider;
- lưu provider message ID khi có;
- phân biệt lỗi chắc chắn thất bại với kết quả không xác định;
- thiết kế email/CTA có thể chịu được việc người nhận nhận trùng khi không thể loại bỏ hoàn toàn.

SMTP thuần không cung cấp một cơ chế idempotency chung bảo đảm exactly-once cho mọi lần gửi. Không nên tuyên bố outbox tự giải quyết gửi trùng.

### 9.1. Tạo ID job ổn định

Ví dụ:

~~~text
order-confirmed:123:version-1
~~~

Nếu cùng một sự kiện xác nhận đơn hàng được xử lý hai lần, hệ thống có thể dùng unique key để tránh insert hai outbox record giống nhau. Cần chọn key theo ý nghĩa nghiệp vụ: nếu khách hàng thật sự cần nhận hai thông báo khác nhau, không được deduplicate chỉ vì cùng order ID.

### 9.2. Lease và nhiều worker

Nếu nhiều worker đọc cùng outbox, cần tránh hai worker cùng gửi một job. Có thể dùng:

- row locking trong transaction ngắn;
- cú pháp `SELECT ... FOR UPDATE SKIP LOCKED` trên database hỗ trợ;
- cột lease/locked-until và token claim;
- queue broker có visibility timeout.

SQL và semantics khóa khác nhau theo database. `SKIP LOCKED` không phải cú pháp portable cho mọi hệ quản trị. Dù dùng cơ chế nào, lease phải hết hạn khi worker chết để job có thể được xử lý lại.

## 10. Chọn snapshot payload hay render lại sau commit?

Nếu worker gửi email sau một khoảng thời gian, dữ liệu trong database có thể thay đổi. Cần quyết định email phải phản ánh **trạng thái tại thời điểm sự kiện** hay **trạng thái mới nhất lúc gửi**.

Ví dụ đơn hàng A123 được xác nhận lúc 10:00 với tổng tiền 220.000 ₫. Lúc 10:05, hệ thống điều chỉnh phí vận chuyển. Worker gửi mail lúc 10:10.

Hai chính sách:

| Chính sách | Dữ liệu email | Phù hợp khi |
| --- | --- | --- |
| Snapshot lúc xác nhận | Tổng tiền 220.000 ₫ theo sự kiện đã phát sinh | Email là bằng chứng/thông báo của một sự kiện cụ thể |
| Đọc dữ liệu mới nhất khi gửi | Tổng tiền theo trạng thái database lúc 10:10 | Email có mục đích hiển thị trạng thái hiện tại |

Nếu dùng snapshot:

- lưu recipient, mã đơn, tiền và dữ liệu cần render trong outbox;
- dùng template version phù hợp;
- tránh phụ thuộc entity đã thay đổi.

Nếu dùng dữ liệu mới nhất:

- chỉ lưu ID và xác định rõ worker sẽ truy vấn lại;
- kiểm tra trạng thái hiện tại trước khi gửi;
- chấp nhận rằng nội dung có thể khác thời điểm tạo event.

Không nên để hành vi này xảy ra ngẫu nhiên do listener hoặc worker truy cập database vào một thời điểm khác nhau.

## 11. Template version và nội dung đã chốt

Outbox có thể lưu:

~~~json
{
  "orderNumber": "A123",
  "customerName": "Nguyễn An",
  "totalText": "220.000 ₫",
  "orderUrl": "https://app.example.com/orders/A123"
}
~~~

Nếu chỉ lưu `templateId` rồi worker dùng template hiện tại, email chờ lâu có thể được render bằng phiên bản mới sau deploy. Đây có thể là hành vi mong muốn, nhưng nếu cần giữ nội dung đã được phê duyệt, hãy lưu thêm `templateVersion` hoặc lưu HTML/text snapshot.

Có ba cách phổ biến:

1. **Snapshot model + template version:** payload giữ dữ liệu đã chụp, worker render đúng phiên bản template.
2. **Snapshot HTML/text:** lưu nội dung hoàn chỉnh đã render; worker chỉ dựng MIME và gửi.
3. **Dữ liệu mới nhất + template mới nhất:** worker đọc lại domain state và dùng mẫu hiện hành; phù hợp khi email phải phản ánh trạng thái mới nhất.

Payload có thể chứa dữ liệu cá nhân; cần giới hạn quyền truy cập, mã hóa storage nếu phù hợp, retention và log tối thiểu.

## 12. So sánh các cách gửi liên quan tới transaction

| Cách làm | Tránh gửi khi DB rollback? | Có thể mất yêu cầu sau process crash? | Có retry bền vững? | Độ phức tạp |
| --- | --- | --- | --- | --- |
| Gọi SMTP trực tiếp trong `@Transactional` | Không | Có | Không tự có | Thấp |
| Bắt lỗi và log trong transaction | Không; email vẫn có thể đi trước commit | Có | Không tự có | Thấp |
| `@TransactionalEventListener(AFTER_COMMIT)` | Có | Có, nếu crash sau commit trước listener | Không tự có | Thấp đến vừa |
| `AFTER_COMMIT` + `@Async` | Có | Có; executor trong process không bền vững | Không tự có | Vừa |
| Transactional outbox + worker | Có, nếu outbox cùng transaction | Yêu cầu gửi được lưu bền vững | Có thể thiết kế | Cao hơn |

### 12.1. Gợi ý chọn cách

- **Demo hoặc thông báo phụ:** có thể gọi trực tiếp nếu chấp nhận tác động ngoài transaction và thời gian chờ.
- **Cần tránh email cho giao dịch rollback, nhưng chấp nhận khả năng mất thông báo hiếm gặp:** dùng `AFTER_COMMIT`.
- **Cần giảm thời gian request chờ SMTP:** có thể dùng listener async, nhưng phải chấp nhận executor không bền vững.
- **Email là một phần quan trọng của quy trình:** dùng transactional outbox với worker, retry, monitoring và chính sách dead-letter.

Không có lựa chọn nào làm SMTP và database trở thành một transaction phân tán nguyên tử. Outbox giúp bảo đảm yêu cầu gửi được lưu cùng thay đổi database, sau đó xử lý giao nhận theo mô hình eventual consistency.

## 13. Kiểm thử hành vi transaction và email

Không nên chỉ mock `JavaMailSender` rồi kiểm tra method được gọi. Cần kiểm tra đúng **thời điểm** gọi mail sender so với commit/rollback.

### 13.1. Test direct send: email được gọi trước commit

Với cách gọi trực tiếp trong method `@Transactional`, có thể kiểm tra rằng sender được gọi trước khi transaction kết thúc. Test này minh họa rủi ro về thứ tự, không cần SMTP thật.

### 13.2. Test AFTER_COMMIT: chỉ gửi sau commit

Một integration test có thể:

1. Gọi application service trong transaction thực.
2. Kiểm tra listener chưa gửi trong khi transaction vẫn hoạt động.
3. Commit transaction.
4. Xác nhận listener được gọi và sender nhận message.

### 13.3. Test rollback: không gửi

Tạo một transaction cập nhật order, publish event rồi buộc rollback:

~~~java
try {
    transactionTemplate.execute(status -> {
        orderService.confirmAndPublish(orderId);
        status.setRollbackOnly();
        return null;
    });
}
~~~

Sau khi transaction kết thúc, xác nhận `JavaMailSender` không được gọi. Listener phase `AFTER_COMMIT` không chạy khi transaction rollback.

### 13.4. Lưu ý về test transaction tự rollback

Spring test thường chạy test trong một transaction và rollback ở cuối. Nếu kiểm tra `@TransactionalEventListener(AFTER_COMMIT)` trong test có transaction mặc định rollback, listener sẽ không chạy.

Để test commit behavior, cần:

- dùng `TransactionTemplate` và để transaction hoàn tất commit;
- hoặc cấu hình test commit có chủ đích, ví dụ `@Commit`;
- hoặc gọi service qua transaction thực được quản lý bởi test setup phù hợp.

Đừng kết luận listener bị lỗi chỉ vì test framework đã rollback transaction.

### 13.5. Test outbox

Với outbox, cần kiểm tra:

- khi order commit, outbox row cũng tồn tại;
- khi order transaction rollback, outbox row không tồn tại;
- worker claim job và gọi MailService;
- lỗi tạm thời tăng attempts và đặt thời điểm retry;
- lỗi vĩnh viễn chuyển trạng thái cuối;
- worker crash sau SMTP submission được xử lý theo chính sách gửi trùng;
- lease hết hạn cho phép worker khác tiếp tục.

Có thể dùng SMTP giả lập như Mailpit hoặc GreenMail để xác nhận MIME được gửi, nhưng test database/outbox vẫn cần kiểm tra trạng thái lưu trữ riêng.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Email xác nhận đã gửi dù order rollback | Gọi SMTP trước commit | Dùng `AFTER_COMMIT` hoặc outbox |
| Order đã commit nhưng email không có | Process dừng sau commit trước khi gửi | Outbox bền vững |
| API trả lỗi nhưng dữ liệu vẫn được lưu | Listener gửi lỗi sau commit và exception truyền về caller | Phân biệt kết quả nghiệp vụ với kết quả thông báo |
| Request chậm khi SMTP chậm | Gửi đồng bộ trong transaction hoặc listener đồng bộ sau commit | Chuyển sang worker/queue nếu cần |
| Email trùng sau retry | SMTP có thể đã nhận nhưng worker chưa ghi trạng thái | Idempotency, provider message ID và trạng thái job |
| `@TransactionalEventListener` không chạy trong test | Test transaction bị rollback | Test với transaction commit thật |
| Listener chạy cả khi không có transaction | Bật `fallbackExecution = true` | Chỉ bật khi đó là chính sách mong muốn |
| Async listener mất event khi restart | Executor chỉ tồn tại trong process | Dùng outbox hoặc queue bền vững |
| Worker không thể render đúng nội dung cũ | Chỉ lưu entity ID và đọc dữ liệu mới nhất | Snapshot payload hoặc template version |
| Outbox job bị hai worker gửi cùng lúc | Claim/lease không được phối hợp | Lock/lease và cơ chế xử lý đồng thời |
| File đính kèm đã bị xóa khi retry | Cleanup sau từng attempt | Giữ artifact đến terminal state |

## 15. Một số lưu ý về transaction propagation

Không nên cố giải quyết vấn đề gửi mail bằng cách tùy tiện thêm `REQUIRES_NEW` hoặc đổi propagation của method.

Ví dụ:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void sendMail(...) {
    mailSender.send(...);
}
~~~

`REQUIRES_NEW` tạo một database transaction riêng khi có transaction bên ngoài. Nhưng SMTP vẫn không tham gia transaction đó. Nó không thể thu hồi email nếu transaction nghiệp vụ rollback và cũng không bảo đảm email được gửi nếu process dừng.

Tương tự, việc đặt `NOT_SUPPORTED` để suspend transaction khi gửi có thể tránh giữ transaction database trong lúc chờ SMTP, nhưng **không tự bảo đảm đúng thứ tự nghiệp vụ**. Nếu dữ liệu chưa commit, mail vẫn có thể được gửi trước khi giao dịch hoàn tất.

Hãy chọn giải pháp theo mục tiêu:

- muốn không gửi khi rollback: thực hiện sau commit;
- muốn không mất yêu cầu sau commit: outbox;
- muốn tránh giữ connection trong lúc SMTP chậm: worker gửi ngoài transaction;
- muốn giảm gửi trùng: idempotency và quản lý trạng thái.

## 16. Tình huống tổng hợp: xác nhận đơn hàng

Giả sử hệ thống cần gửi email xác nhận sau khi order được chuyển sang `CONFIRMED`.

### 16.1. Phiên bản trực tiếp

~~~text
@Transactional confirmOrder()
  -> load order
  -> update order
  -> create SimpleMailMessage
  -> JavaMailSender.send()
  -> method returns
  -> DB commit
~~~

Đơn giản, nhưng email có thể đi trước commit; SMTP chậm kéo dài transaction.

### 16.2. Phiên bản AFTER_COMMIT

~~~text
@Transactional confirmOrder()
  -> update order
  -> publish OrderConfirmedEvent
  -> DB commit
  -> listener receives event
  -> JavaMailSender.send()
~~~

Không gửi khi rollback. Vẫn có khoảng trống sau commit trước khi listener hoàn tất; event trong bộ nhớ có thể mất nếu process dừng.

### 16.3. Phiên bản transactional outbox

~~~text
@Transactional confirmOrder()
  -> update order
  -> insert mail_outbox snapshot
  -> DB commit

Mail worker
  -> claim outbox row
  -> render template
  -> send through MailService
  -> update SUBMITTED or RETRY_WAIT
  -> cleanup artifact when terminal
~~~

Order và yêu cầu gửi được lưu cùng transaction. Worker có thể tiếp tục sau khi ứng dụng restart, retry lỗi tạm thời và đưa lỗi vĩnh viễn vào quy trình xử lý. Cần thiết kế chống gửi trùng vì SMTP submission và cập nhật trạng thái outbox không phải một giao dịch nguyên tử.

## 17. Những điều cần nhớ

- SMTP không tham gia database transaction của Spring.
- Gọi `JavaMailSender.send` trong `@Transactional` có thể gửi email trước khi database commit.
- Nếu transaction rollback sau khi SMTP chấp nhận thư, email không thể được thu hồi bằng rollback.
- Nếu gửi lỗi và exception thoát khỏi method, Spring có thể rollback transaction; đây là quyết định nghiệp vụ cần cân nhắc.
- Gửi sau commit giúp tránh thông báo cho giao dịch rollback, nhưng event trong bộ nhớ vẫn có thể mất khi process dừng.
- `@Async` giảm thời gian chờ nhưng không tạo queue bền vững.
- Transactional outbox lưu yêu cầu gửi cùng transaction nghiệp vụ, rồi worker gửi và retry sau commit.
- Outbox thường cung cấp xử lý at-least-once; vẫn cần xử lý gửi trùng và kết quả SMTP không xác định.
- Ghi rõ trạng thái `SUBMITTED` thay vì khẳng định `DELIVERED` khi chỉ biết sender đã nộp thư.

Khi thiết kế gửi email quanh một transaction nghiệp vụ, hãy xác định trước điều gì phải được bảo đảm: không gửi khi rollback, không mất yêu cầu sau commit, thời gian phản hồi, hay khả năng retry. Gửi trực tiếp trong transaction có thể phù hợp với tác vụ đơn giản và ít quan trọng, nhưng với thông báo gắn chặt với trạng thái nghiệp vụ, `AFTER_COMMIT` hoặc transactional outbox tạo ra ranh giới rõ ràng hơn giữa **commit dữ liệu** và **gửi thông báo**.

### Tài liệu tham khảo

- **Spring Framework Reference — Transaction Management:** transaction boundaries, rollback rules và transaction synchronization.
- **Spring Framework Reference — Transaction-bound Events:** `@TransactionalEventListener` và các phase `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`.
- **Spring Framework Reference — Application Events:** `ApplicationEventPublisher` và listener.
- **Spring Framework Reference — Task Execution and Scheduling:** `@Async` và executor.
- **Spring Framework API — `TransactionSynchronizationManager`:** đăng ký callback theo vòng đời transaction.
- **Transactional Outbox Pattern:** lưu event/job cùng transaction dữ liệu và relay xử lý sau commit.
- **RFC 5321 — Simple Mail Transfer Protocol:** phản hồi SMTP và quá trình tiếp nhận message.
