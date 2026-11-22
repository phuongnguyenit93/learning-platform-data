# Tách giao dịch dữ liệu khỏi giao dịch SMTP

Trong một ứng dụng Spring, việc cập nhật dữ liệu nghiệp vụ và gửi email thường xảy ra trong cùng một luồng xử lý. Ví dụ, khi xác nhận đơn hàng, ứng dụng cập nhật trạng thái trong database rồi gửi email cho khách hàng. Tuy nhiên, hai thao tác này thuộc hai hệ thống khác nhau: database quản lý transaction dữ liệu, còn SMTP thực hiện việc chuyển message tới mail server.

**Transaction database không bao gồm transaction SMTP.** Nếu SMTP server đã chấp nhận email rồi database rollback, email vẫn có thể đến người nhận. Ngược lại, database có thể commit thành công nhưng việc gửi SMTP thất bại. Không có một transaction cục bộ của Spring nào tự động làm cho hai kết quả này nguyên tử.

Vì vậy, cần tách ranh giới dữ liệu khỏi ranh giới gửi thư và xác định cách phối hợp giữa chúng. Với ứng dụng đơn giản, có thể commit dữ liệu trước rồi mới gọi mail service. Với email cần chạy sau commit, có thể dùng sự kiện AFTER_COMMIT. Với thông báo quan trọng cần sống sót qua restart và có thể retry, transactional outbox thường là lựa chọn phù hợp.

## 1. Hai loại giao dịch có mục tiêu khác nhau

### 1.1. Transaction dữ liệu

Transaction dữ liệu thường được quản lý bởi Spring transaction abstraction và một transaction manager như DataSourceTransactionManager hoặc JpaTransactionManager.

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    orderHistoryRepository.save(
            OrderHistory.confirmed(orderId)
    );
}
~~~

Các thao tác database trong cùng transaction có thể được commit hoặc rollback theo quy tắc của database. Nếu cập nhật đơn hàng hoặc ghi lịch sử thất bại, transaction có thể rollback để không để lại trạng thái dở dang.

Transaction dữ liệu quan tâm đến tính nhất quán của những thay đổi nằm trong cùng resource transaction.

### 1.2. Giao dịch gửi SMTP

SMTP có một chuỗi lệnh để chuyển message tới mail server. Ở mức khái quát, client kết nối, xác thực nếu cần, khai báo người gửi và người nhận, truyền nội dung rồi nhận phản hồi từ server.

~~~text
SMTP client
    |
    +-- Connect / TLS / AUTH
    +-- MAIL FROM
    +-- RCPT TO
    +-- DATA
    +-- Message content
    +-- End of DATA
    |
    v
SMTP server response
~~~

Khi SMTP server chấp nhận message sau bước DATA, server nhận trách nhiệm xử lý tiếp theo theo giao thức và chính sách của nó. Điều này không có nghĩa message chắc chắn đã vào inbox hoặc người nhận đã đọc.

SMTP session/transaction có phạm vi riêng của giao thức mail. Nó không phải transaction JDBC và không được Spring database transaction manager tự động quản lý.

### 1.3. Vì sao hai transaction không nguyên tử?

Một transaction nguyên tử cần có cơ chế phối hợp để commit hoặc rollback tất cả resource tham gia. Database có thể hỗ trợ transaction cục bộ trên connection của nó. SMTP server thông thường không cung cấp XA resource để tham gia distributed two-phase commit cùng database.

Vì vậy, đoạn code sau:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    // Update database
    // Send SMTP email
}
~~~

không tạo ra một transaction phân tán bao trùm cả database và SMTP. Annotation chỉ quản lý các thao tác được transaction manager hỗ trợ; lời gọi JavaMailSender là I/O bên ngoài.

## 2. Dual-write: ghi database và gửi email là hai lần ghi độc lập

Khi một use case vừa ghi database vừa gửi email, ứng dụng đang thực hiện hai side effect:

1. Ghi trạng thái nghiệp vụ vào database.
2. Gửi message qua SMTP.

Đây là một dạng **dual-write problem**. Hai lần ghi không cùng commit nguyên tử, nên luôn có khoảng thời gian mà một bên thành công còn bên kia chưa hoàn tất.

### 2.1. Gửi SMTP trước rồi commit database

~~~text
BEGIN database transaction
    UPDATE order -> CONFIRMED
    SMTP accepts confirmation email
COMMIT database transaction
~~~

Nếu commit thất bại:

~~~text
Database: rollback
SMTP: message đã được chấp nhận
~~~

Người nhận có thể nhận email xác nhận cho một thay đổi không tồn tại trong database.

### 2.2. Commit database trước rồi gửi SMTP

~~~text
BEGIN database transaction
    UPDATE order -> CONFIRMED
COMMIT database transaction

SMTP sends confirmation email
~~~

Nếu SMTP thất bại:

~~~text
Database: CONFIRMED
SMTP: send failed
~~~

Trạng thái nghiệp vụ đã được lưu, nhưng email chưa được gửi. Đây thường là hướng tốt hơn về tính đúng đắn của nghiệp vụ: thông báo chỉ được gửi sau khi thay đổi đã commit. Tuy nhiên, nếu process dừng giữa commit và lời gọi SMTP, ý định gửi có thể bị mất nếu chưa được lưu ở đâu đó.

### 2.3. Bảng các cửa sổ lỗi

| Thời điểm lỗi | Trạng thái database | Trạng thái SMTP | Hệ quả |
| --- | --- | --- | --- |
| Database lỗi trước khi gọi SMTP | Rollback | Chưa gửi | Không có email sai trạng thái |
| SMTP chấp nhận trước khi database commit lỗi | Rollback | Có thể đã nhận message | Email thông báo thay đổi chưa commit |
| Database commit, SMTP từ chối | Đã commit | Gửi thất bại | Nghiệp vụ hoàn tất nhưng thiếu thông báo |
| Database commit, process dừng trước send | Đã commit | Chưa gửi | Có thể mất ý định gửi |
| SMTP chấp nhận, process dừng trước khi lưu kết quả | Đã commit | Có thể đã nhận message | Retry có thể gửi trùng |
| SMTP timeout với kết quả không rõ | Tùy thời điểm | Không xác định | Retry cần thận trọng |

Mục tiêu của thiết kế là chọn thứ tự và cơ chế lưu trạng thái sao cho các cửa sổ lỗi có thể được phát hiện và xử lý.

## 3. Không gọi JavaMailSender bên trong transaction dữ liệu

Một ví dụ dễ gặp:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final JavaMailSender mailSender;

    public OrderService(
            OrderRepository orderRepository,
            JavaMailSender mailSender
    ) {
        this.orderRepository = orderRepository;
        this.mailSender = mailSender;
    }

    @Transactional
    public void confirmOrder(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        sendConfirmation(order);
    }

    private void sendConfirmation(Order order) {
        // Create MimeMessage and call mailSender.send(...)
    }
}
~~~

Vấn đề không nằm ở cú pháp JavaMailSender. Vấn đề là SMTP được gọi trong lúc transaction database còn mở.

Có ba rủi ro:

- SMTP chậm làm transaction giữ connection và lock lâu hơn.
- Email có thể được chấp nhận rồi transaction rollback.
- Lỗi SMTP có thể làm nghiệp vụ rollback theo rollback rule dù dữ liệu vốn có thể commit hợp lệ.

Không nên coi việc chuyển lời gọi send xuống một private method là đã tách transaction. Method đó vẫn chạy trong cùng luồng và cùng transaction của caller.

## 4. Tách application service và mail service

Một cách tổ chức rõ ràng là để service nghiệp vụ chỉ cập nhật dữ liệu, còn service gửi mail chỉ xử lý message.

~~~text
OrderApplicationService
        |
        v
OrderService
    @Transactional
        |
        +-- Validate
        +-- Update order
        +-- Build mail snapshot
        |
        v
      COMMIT
        |
        v
OrderMailService
        |
        +-- Render template
        +-- Create MimeMessage
        +-- Send via JavaMailSender
~~~

Ví dụ DTO snapshot:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String totalAmount
) {}
~~~

Service dữ liệu:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderMailData confirm(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        return new OrderMailData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getNumber(),
                order.getTotal().toPlainString()
        );
    }
}
~~~

Service điều phối:

~~~java
@Service
public class OrderConfirmationFacade {

    private final OrderService orderService;
    private final OrderMailService mailService;

    public OrderConfirmationFacade(
            OrderService orderService,
            OrderMailService mailService
    ) {
        this.orderService = orderService;
        this.mailService = mailService;
    }

    public void confirmAndNotify(UUID orderId) {
        OrderMailData snapshot = orderService.confirm(orderId);

        // Lời gọi transactional đã trả về sau commit thành công.
        mailService.sendConfirmation(snapshot);
    }
}
~~~

Vì OrderService là một bean riêng được gọi qua Spring proxy, transaction có thể hoàn tất trước khi facade tiếp tục. Nếu commit ném lỗi, lời gọi không trả về bình thường và facade không gọi mail service.

### 4.1. Vì sao nên trả về DTO?

Không nên giữ JPA entity rồi chuyển sang mail service sau transaction. Entity có thể detached khỏi persistence context; quan hệ lazy có thể không còn truy cập được.

DTO snapshot giữ đúng dữ liệu cần để dựng email tại thời điểm nghiệp vụ được xác nhận. Nó cũng giúp renderer không phụ thuộc repository hoặc Hibernate session.

### 4.2. Giới hạn của cách gọi tuần tự

Cách này đảm bảo send chỉ được gọi sau khi service transactional trả về thành công. Tuy nhiên, có một khoảng trống:

~~~text
1. Database commit thành công.
2. Process dừng trước khi mailService.sendConfirmation().
3. Không có email và không có bản ghi công việc để retry.
~~~

Nếu email chỉ mang tính tiện ích, có thể chấp nhận rủi ro này. Nếu thông báo là một phần quan trọng của nghiệp vụ, cần lưu ý định gửi trong database hoặc một hàng đợi bền vững.

## 5. AFTER_COMMIT: gắn gửi mail với thời điểm commit thành công

Spring hỗ trợ **@TransactionalEventListener** để xử lý event theo vòng đời transaction.

Sự kiện:

~~~java
public record OrderConfirmedEvent(
        OrderMailData mailData
) {}
~~~

Service nghiệp vụ:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher publisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher publisher
    ) {
        this.orderRepository = orderRepository;
        this.publisher = publisher;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        OrderMailData snapshot = new OrderMailData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getNumber(),
                order.getTotal().toPlainString()
        );

        publisher.publishEvent(
                new OrderConfirmedEvent(snapshot)
        );
    }
}
~~~

Listener:

~~~java
@Component
public class OrderMailListener {

    private final OrderMailService mailService;

    public OrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(event.mailData());
    }
}
~~~

Luồng:

~~~text
@Transactional confirm()
        |
        +-- Update database
        +-- Publish event
        |
        v
    COMMIT
        |
        +-- Success
        |     |
        |     v
        |  AFTER_COMMIT listener
        |     |
        |     v
        |  SMTP send
        |
        +-- Rollback
              |
              v
        Listener không chạy
~~~

Event được publish trong transaction, nhưng listener chỉ xử lý sau khi commit thành công. Nếu transaction rollback, listener AFTER_COMMIT không gửi email.

### 5.1. Không dùng BEFORE_COMMIT cho email xác nhận

**BEFORE_COMMIT** chạy trước khi database xác nhận commit. Transaction vẫn có thể thất bại sau listener. Nếu listener gửi email ở phase này, rủi ro email đã gửi nhưng dữ liệu rollback vẫn còn.

Với email khẳng định một thay đổi đã lưu thành công, dùng AFTER_COMMIT.

### 5.2. Event không có transaction

Theo mặc định, TransactionalEventListener yêu cầu transaction đang hoạt động khi event được publish. Nếu không có transaction, listener có thể không chạy.

Có tùy chọn **fallbackExecution = true**, nhưng chỉ bật nếu nghiệp vụ cho phép listener chạy cả khi event không gắn với transaction. Không dùng tùy chọn này chỉ để che lỗi publish event sai ranh giới.

### 5.3. AFTER_COMMIT không lưu event bền vững

Application event thông thường tồn tại trong process. Nếu database commit xong rồi process crash trước khi listener xử lý, event có thể mất.

Do đó, AFTER_COMMIT đảm bảo thứ tự xử lý khi ứng dụng đang hoạt động; nó không bảo đảm worker sẽ khôi phục event sau restart.

## 6. Tách gửi SMTP sang thread khác với @Async

Nếu không muốn request HTTP chờ SMTP, có thể kết hợp AFTER_COMMIT với **@Async**.

Cấu hình executor:

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public Executor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-worker-");
        return executor;
    }
}
~~~

Listener:

~~~java
@Component
public class AsyncOrderMailListener {

    private final OrderMailService mailService;

    public AsyncOrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @Async("mailExecutor")
    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(event.mailData());
    }
}
~~~

Sau commit, listener chuyển tác vụ sang executor. Thread xử lý request không phải chờ việc gửi SMTP hoàn tất nếu luồng gọi không chờ kết quả async.

### 6.1. Ba khái niệm cần phân biệt

| Cơ chế | Trách nhiệm |
| --- | --- |
| AFTER_COMMIT | Chỉ xử lý event sau commit thành công |
| @Async | Chạy xử lý trên executor khác |
| Transactional outbox | Lưu ý định xử lý bền vững cùng transaction dữ liệu |

@Async không tự retry. Task trong executor cũng có thể mất khi process dừng hoặc bị từ chối nếu queue đầy. Nếu email quan trọng, cần lưu trạng thái bền vững và có worker phục hồi.

### 6.2. Không truyền entity sang async worker

Worker chạy trên thread khác và không kế thừa persistence context của thread nghiệp vụ. Hãy truyền DTO snapshot có thể serialize, hoặc truyền business ID và để worker mở transaction riêng khi cần đọc dữ liệu.

## 7. Transactional outbox: phối hợp hai giao dịch bằng một bản ghi bền vững

Khi email phải được xử lý ngay cả khi ứng dụng restart, có thể dùng **transactional outbox**.

Trong cùng transaction database, ứng dụng:

1. Cập nhật dữ liệu nghiệp vụ.
2. Tạo một bản ghi outbox mô tả email cần gửi.
3. Commit cả hai thay đổi.

~~~text
BEGIN DATABASE TRANSACTION
    UPDATE orders SET status = 'CONFIRMED'
    INSERT INTO mail_outbox (..., status = 'PENDING')
COMMIT
~~~

Sau commit, một worker đọc outbox và thực hiện giao dịch SMTP ở bước riêng:

~~~text
Database transaction
       |
       +-- Update order
       +-- Insert outbox event
       |
       v
     COMMIT
       |
       v
Outbox worker
       |
       +-- Claim event
       +-- Render email
       +-- Send SMTP
       +-- Save result
~~~

Nếu transaction rollback, cả order update và outbox row đều rollback. Nếu commit thành công, outbox row vẫn tồn tại trong database để worker xử lý sau khi process khởi động lại.

### 7.1. Bảng outbox minh họa

~~~sql
CREATE TABLE mail_outbox (
    id              UUID PRIMARY KEY,
    event_type      VARCHAR(100) NOT NULL,
    payload         TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    created_at      TIMESTAMP NOT NULL,
    sent_at         TIMESTAMP NULL,
    last_error      TEXT NULL
);
~~~

Schema thực tế có thể thêm template key/version, locale, correlation ID, lease owner, lease expiry, recipient reference và loại lỗi đã phân loại.

Payload nên là DTO/event schema rõ ràng. Không serialize toàn bộ JPA entity vào outbox vì entity có thể chứa quan hệ vòng, lazy proxy và dữ liệu không cần thiết.

### 7.2. Ghi outbox cùng dữ liệu nghiệp vụ

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    OrderMailData snapshot = new OrderMailData(
            order.getCustomerEmail(),
            order.getCustomerName(),
            order.getNumber(),
            order.getTotal().toPlainString()
    );

    outboxRepository.save(
            MailOutboxEvent.pending(
                    UUID.randomUUID(),
                    "ORDER_CONFIRMED",
                    serialize(snapshot)
            )
    );
}
~~~

Trong phương thức này không gọi JavaMailSender. Database transaction quản lý cả cập nhật order và ý định gửi email.

### 7.3. Worker xử lý outbox

Pseudo-code:

~~~java
public void processPendingBatch() {
    List<MailOutboxEvent> events =
            outboxRepository.claimPendingBatch(50);

    for (MailOutboxEvent event : events) {
        try {
            OrderMailData data = deserialize(event.payload());

            mailService.sendConfirmation(data);

            outboxRepository.markSent(event.id());
        } catch (Exception ex) {
            outboxRepository.scheduleRetry(
                    event.id(),
                    calculateNextAttempt(event.attempts()),
                    classify(ex)
            );
        }
    }
}
~~~

Đây là ví dụ mô tả luồng. Implementation thật cần cơ chế claim hoặc lease để nhiều worker không xử lý cùng event đồng thời. Cũng cần transaction riêng cho việc claim và cập nhật trạng thái.

### 7.4. Không giữ transaction database trong lúc chờ SMTP

Worker nên claim event trong một transaction ngắn, commit claim, sau đó gửi SMTP ngoài transaction đó. Khi có kết quả, worker mở transaction khác để cập nhật SENT hoặc lịch retry.

Như vậy, lock database không bị giữ trong suốt thời gian network I/O. Nếu worker crash sau SMTP accept nhưng trước khi cập nhật kết quả, lease có thể hết hạn và event được xử lý lại; cần có chính sách duplicate handling.

## 8. SMTP accept và database status là hai mốc khác nhau

Một email có thể trải qua nhiều trạng thái:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP accepted --> SENT_TO_PROVIDER
   |
   +-- Temporary error --> RETRY_WAIT
   |
   +-- Permanent error --> FAILED
~~~

Tên trạng thái nên mô tả chính xác điều hệ thống biết.

| Trạng thái | Ý nghĩa |
| --- | --- |
| PENDING | Ý định gửi đã được lưu |
| PROCESSING | Worker đã claim tác vụ |
| RETRY_WAIT | Lỗi tạm thời, chờ lần thử tiếp theo |
| SENT_TO_PROVIDER | SMTP/provider đã chấp nhận message theo phản hồi |
| FAILED | Tác vụ không thể tiếp tục theo policy |
| DELIVERY_CONFIRMED | Có tín hiệu chuyển phát theo định nghĩa của provider |

Không nên dùng SENT để ngụ ý người nhận đã đọc thư. SMTP accept không chứng minh message đã tới inbox, không bị lọc spam hoặc đã được người nhận mở.

### 8.1. Lưu kết quả sau khi gọi SMTP

Một luồng thông thường:

1. Worker claim event.
2. Gửi message.
3. Nếu JavaMailSender trả về bình thường, ghi nhận SMTP/provider đã chấp nhận theo mức xác nhận của transport.
4. Nếu send ném lỗi, phân loại lỗi và lên lịch retry hoặc đánh dấu failed.

Không đánh dấu SENT trước khi gọi send. Nếu ghi SENT rồi process crash trước khi gửi, email bị mất nhưng database lại ghi đã gửi.

### 8.2. Kết quả không xác định

Nếu kết nối bị ngắt trong lúc SMTP server có thể đã nhận nội dung, ứng dụng có thể không biết message đã được chấp nhận hay chưa.

Retry có thể gửi trùng. Không retry có thể bỏ lỡ message nếu server chưa nhận. Đây là giới hạn khi phối hợp database và SMTP mà không có transaction chung.

## 9. Outbox cung cấp at-least-once processing, không phải exactly-once email

Xét tình huống:

~~~text
1. Worker đọc event PENDING.
2. SMTP server trả phản hồi chấp nhận message.
3. Worker crash trước khi cập nhật outbox thành SENT.
4. Lease hết hạn.
5. Worker khác claim lại event.
6. SMTP nhận message lần nữa.
~~~

Người nhận có thể nhận hai email. Transactional outbox giúp không mất ý định gửi sau commit, nhưng không thể làm cho SMTP và database commit nguyên tử.

### 9.1. Event ID ổn định

Mỗi ý định gửi cần có ID ổn định để theo dõi outbox row, correlation log, số lần retry, kết quả gửi và đối soát vận hành.

Không tạo ID mới cho mỗi lần retry cùng một ý định.

### 9.2. Message-ID không bảo đảm chống trùng

Email có header Message-ID hữu ích cho tra cứu và đối soát. Nhưng SMTP server và email client không bắt buộc phải loại bỏ các message trùng chỉ vì chúng có cùng Message-ID.

Nếu provider hỗ trợ idempotency key qua API riêng, có thể dùng theo hợp đồng của provider. SMTP thuần không có cơ chế exactly-once tổng quát.

### 9.3. Idempotency ở tầng nghiệp vụ

Có thể dùng event key ổn định, ví dụ:

~~~text
ORDER_CONFIRMED:order-1001:version-3
~~~

Unique constraint trên event key giúp tránh tạo nhiều outbox row cho cùng một lần chuyển trạng thái. Worker cũng có thể kiểm tra trạng thái xử lý trước khi claim.

Tuy nhiên, idempotency trong database không thể biết chắc SMTP đã nhận message khi kết nối bị mất sau DATA. Cần thiết kế nội dung chịu được gửi lặp và có cách đối soát.

## 10. Retry và backoff cho giao dịch SMTP

Không nên retry liên tục trong vòng lặp ngắn. Điều đó có thể làm SMTP provider quá tải, tăng nguy cơ bị giới hạn tốc độ hoặc tạo nhiều email trùng.

Một lịch retry có thể dùng exponential backoff:

~~~text
Lần 1: chờ ngắn
Lần 2: chờ lâu hơn
Lần 3: chờ lâu hơn nữa
...
Đạt giới hạn: FAILED hoặc dead-letter
~~~

Thời gian thực tế phụ thuộc loại lỗi, SLA và chính sách provider. Có thể thêm jitter để nhiều worker không retry đồng thời.

### 10.1. Phân loại lỗi

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Tạm thời | SMTP 4xx, server bận, timeout có thể retry | Backoff và thử lại theo giới hạn |
| Vĩnh viễn | Recipient không hợp lệ hoặc bị policy từ chối cố định | Đánh dấu lỗi, không retry vô hạn |
| Không xác định | Mất kết nối sau khi server có thể đã nhận DATA | Xử lý thận trọng vì có thể gửi trùng |
| Lỗi tạo message | Template lỗi, attachment không tồn tại | Sửa nguồn dữ liệu/template trước khi retry |

Không phải mọi MailException đều có cùng tính chất. Cần xem root cause, phản hồi SMTP và loại thao tác thất bại.

### 10.2. Giới hạn số lần thử và dead-letter

Sau số lần retry tối đa, event có thể chuyển sang FAILED hoặc dead-letter để người vận hành xem xét. Cần lưu nguyên nhân, thời điểm, attempts và correlation ID để có thể xử lý.

Không retry vô hạn recipient sai hoặc template hỏng. Retry chỉ hữu ích khi nguyên nhân có khả năng được khắc phục mà không cần thay đổi dữ liệu đầu vào.

## 11. Vì sao không dùng JTA/XA để gom SMTP và database?

JTA/XA có thể phối hợp một số resource manager hỗ trợ XA trong distributed transaction. Ví dụ, hai database hoặc database và một message broker có hỗ trợ XA có thể tham gia two-phase commit trong môi trường phù hợp.

SMTP server thông thường không cung cấp XAResource để tham gia transaction manager của ứng dụng. Vì vậy, việc bật JTA không tự biến JavaMailSender thành một participant có thể prepare/commit/rollback cùng database.

Ngoài ra, distributed transaction có chi phí vận hành, thời gian giữ resource và failure mode riêng. Với email, outbox thường là cách thực tế hơn để lưu ý định gửi cùng dữ liệu rồi thực hiện SMTP sau commit.

Không nên nhầm SMTP protocol transaction với XA transaction. Từ “transaction” trong SMTP mô tả chuỗi thao tác chuyển một message tới server, không có nghĩa nó là một resource có thể rollback cùng database.

## 12. Transaction synchronization là một lựa chọn callback sau commit

Ngoài event listener, Spring có **TransactionSynchronizationManager** để đăng ký callback theo vòng đời transaction.

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    OrderMailData snapshot = toMailData(order);

    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    mailService.sendConfirmation(snapshot);
                }
            }
    );
}
~~~

Callback afterCommit chỉ được gọi sau khi transaction commit thành công. Cần bảo đảm transaction synchronization đang hoạt động trước khi đăng ký callback.

### 12.1. Giới hạn của callback

Transaction synchronization vẫn chạy trong process. Nếu process dừng sau commit nhưng trước callback, email có thể không được gửi. Nó giải quyết thứ tự thực thi, không cung cấp durability.

Nếu callback cần ghi một trạng thái database mới, cần chú ý transaction gốc đã commit. Có thể dùng một bean riêng với **Propagation.REQUIRES_NEW** khi thật sự cần transaction mới cho thao tác ghi trạng thái sau commit.

## 13. Xử lý exception và rollback rule của Spring

Theo quy tắc mặc định phổ biến của Spring, transaction rollback khi phương thức transactional kết thúc bằng RuntimeException hoặc Error. Checked exception không tự động kích hoạt rollback theo cùng quy tắc mặc định, trừ khi có rollback rule phù hợp.

~~~java
@Transactional
public void confirmOrder(UUID orderId) throws MessagingException {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    mailService.sendConfirmation(order);
}
~~~

Nếu MessagingException là checked exception và được ném ra, transaction không nhất thiết rollback theo mặc định. Nếu exception được wrap thành RuntimeException hoặc cấu hình rollbackFor tương ứng, transaction có thể rollback.

Điều này ảnh hưởng cách xử lý khi send thất bại, nhưng không giải quyết được trường hợp SMTP đã chấp nhận message rồi một lỗi khác làm transaction rollback.

### 13.1. rollbackFor không tạo transaction phân tán

~~~java
@Transactional(rollbackFor = Exception.class)
public void confirmOrder(UUID orderId) {
    // ...
}
~~~

Cấu hình này thay đổi điều kiện rollback của database transaction. Nó không khiến SMTP trở thành resource được rollback cùng database.

Nếu SMTP đã nhận message, database rollback vẫn không thể thu hồi message.

### 13.2. Bắt lỗi SMTP rồi bỏ qua

~~~java
try {
    mailService.sendConfirmation(data);
} catch (MailException ex) {
    log.warn("Cannot send confirmation", ex);
}
~~~

Bắt exception có thể ngăn lỗi gửi làm rollback nghiệp vụ, nhưng nếu không lưu trạng thái và không có cơ chế retry, thông báo có thể mất. Cần quyết định email là best-effort hay là một nghĩa vụ phải được theo dõi tới khi xử lý xong.

## 14. Tổ chức snapshot và dữ liệu cho worker

Khi tách dữ liệu khỏi SMTP, cần quyết định worker nhận snapshot hay đọc lại database.

| Cách truyền dữ liệu | Ý nghĩa | Phù hợp |
| --- | --- | --- |
| Snapshot DTO | Dữ liệu tại thời điểm transaction tạo event | Xác nhận đơn hàng, hóa đơn, biên nhận |
| Business ID | Worker đọc trạng thái mới nhất | Nhắc nhở hoặc thông báo cần dữ liệu hiện tại |
| Snapshot + template version | Có thể dựng lại nội dung theo phiên bản đã chọn | Email cần kiểm toán hoặc tái tạo |

Ví dụ snapshot:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        BigDecimal total,
        Instant confirmedAt,
        String locale
) {}
~~~

Không nên lưu toàn bộ entity hoặc thông tin không cần thiết. Payload outbox có thể chứa dữ liệu cá nhân, nên cần phân quyền, retention và mã hóa phù hợp với chính sách ứng dụng.

### 14.1. Render template ở đâu?

Có thể render sau khi service transactional trả về, trong AFTER_COMMIT listener, trong async worker hoặc trong outbox worker.

Nếu template chỉ dùng DTO snapshot và không cần database, render có thể chạy ngoài transaction dữ liệu. Nếu worker cần truy vấn dữ liệu, hãy mở transaction đọc riêng và xác định rõ snapshot hay trạng thái mới nhất là yêu cầu nghiệp vụ.

### 14.2. Không để SMTP service sở hữu nghiệp vụ

Mail service nên nhận dữ liệu đã được chuẩn bị, dựng MIME và gửi. Nó không nên tự quyết định đơn hàng có được xác nhận hay không, trừ khi đó là một phần rõ ràng của orchestration.

Việc tách trách nhiệm giúp retry SMTP mà không chạy lại toàn bộ nghiệp vụ.

## 15. Trạng thái nghiệp vụ và trạng thái gửi mail nên độc lập

Một đơn hàng có thể đã xác nhận dù email đang chờ gửi:

~~~text
Order:
  status = CONFIRMED

Mail delivery:
  status = PENDING
~~~

Đây là trạng thái hợp lệ nếu nghiệp vụ xác định commit đơn hàng là kết quả chính, còn email là tác vụ thông báo cần xử lý tiếp.

Không nên ép trạng thái order quay về PENDING chỉ vì SMTP tạm thời không hoạt động, trừ khi quy trình nghiệp vụ thật sự định nghĩa việc gửi email là điều kiện hoàn tất.

Có thể theo dõi riêng:

| Đối tượng | Trạng thái ví dụ |
| --- | --- |
| Order | PENDING, CONFIRMED, CANCELLED |
| Mail event | PENDING, PROCESSING, RETRY_WAIT, SENT_TO_PROVIDER, FAILED |

Việc tách trạng thái giúp hệ thống hiển thị đúng: đơn hàng đã xác nhận, email chưa gửi hoặc đang retry.

## 16. Kiểm thử hai ranh giới giao dịch

Các test cần kiểm tra cả transaction dữ liệu và giao dịch SMTP theo từng failure window.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Database rollback trước commit | Không phát lệnh gửi sau commit |
| Database commit thành công | Listener/worker được phép xử lý email |
| SMTP từ chối sau commit | Dữ liệu nghiệp vụ vẫn đã commit |
| Process dừng sau commit với AFTER_COMMIT in-memory | Có thể mất event; test thể hiện giới hạn này |
| Outbox insert cùng transaction rồi rollback | Không có business update và outbox row |
| Outbox commit rồi worker restart | Event còn tồn tại và có thể được xử lý |
| SMTP accept rồi worker crash trước mark SENT | Có thể gửi trùng khi retry |
| Hai worker cùng xử lý một event | Claim/lease ngăn xử lý đồng thời theo thiết kế |

### 16.1. Test AFTER_COMMIT

Một integration test nên có transaction commit thực sự để xác nhận listener được gọi. Test rollback xác nhận listener AFTER_COMMIT không chạy.

Nếu test framework tự rollback transaction sau mỗi test, listener có thể không được gọi vì không có commit thành công. Hãy chủ động commit trong test cần kiểm tra phase AFTER_COMMIT.

### 16.2. Test outbox atomicity

Kiểm tra hai tình huống:

- Commit: business row và outbox row cùng tồn tại.
- Rollback: cả hai thay đổi đều không tồn tại.

Đây là thuộc tính quan trọng nhất của outbox. Nó bảo đảm ý định gửi không bị tách khỏi thay đổi dữ liệu đã commit.

### 16.3. Test SMTP bằng capture server

Dùng SMTP capture server trong môi trường test để quan sát message mà không gửi tới mailbox thật. Có thể kiểm tra recipient, subject, body, attachment và số message được nhận.

Để mô phỏng duplicate window, cho worker dừng sau khi SMTP capture server nhận message nhưng trước khi trạng thái outbox được cập nhật. Khi worker chạy lại, test có thể chứng minh vì sao duplicate vẫn có thể xảy ra.

## 17. Chọn cách phối hợp theo yêu cầu

| Yêu cầu | Cách triển khai phù hợp | Giới hạn |
| --- | --- | --- |
| Email tiện ích, có thể chấp nhận mất hiếm gặp | Gọi mail service sau transactional service return | Process có thể dừng trước send |
| Chỉ cần gửi sau commit | AFTER_COMMIT event hoặc transaction callback | Event in-memory không durable |
| Request không nên chờ SMTP | AFTER_COMMIT kết hợp @Async | Task có thể mất khi process dừng |
| Email quan trọng cần phục hồi sau restart | Transactional outbox | Có thể gửi trùng ở failure window |
| Cần retry và lịch sử từng lần gửi | Outbox/queue với trạng thái và backoff | Cần worker, lease và vận hành |
| Email phải phản ánh dữ liệu tại thời điểm giao dịch | Snapshot DTO trong transaction | Cần bảo vệ payload và retention |
| Email cần trạng thái mới nhất | Worker reload theo business ID | Nội dung có thể khác thời điểm phát event |

Không phải email nào cũng cần outbox. Hãy căn cứ vào hậu quả nếu email mất, thời gian phản hồi cần đạt, lưu lượng gửi và khả năng vận hành worker.

## 18. Những sai lầm thường gặp

| Sai lầm | Vì sao không giải quyết được | Cách xử lý |
| --- | --- | --- |
| Gửi ở dòng cuối @Transactional | Commit vẫn xảy ra sau method body | Gửi sau commit |
| Dùng @Async trực tiếp trong transaction | Task có thể chạy trước commit | Kết hợp AFTER_COMMIT hoặc outbox |
| Dùng BEFORE_COMMIT | Commit vẫn có thể thất bại sau callback | Dùng AFTER_COMMIT |
| Dùng REQUIRES_NEW cho mail service | Chỉ tạo transaction DB mới, SMTP vẫn bên ngoài | Tách thời điểm gửi khỏi transaction nghiệp vụ |
| Bắt exception và bỏ qua | Không có cơ chế retry hoặc theo dõi | Lưu trạng thái lỗi và retry theo policy |
| Nghĩ outbox bảo đảm exactly-once | Worker có thể crash sau SMTP accept | Thiết kế duplicate handling |
| Truyền JPA entity sang worker | Entity có thể detached/lazy | Truyền DTO snapshot |
| Giữ transaction khi chờ SMTP | Tăng thời gian giữ connection/lock | Claim ngắn, gửi ngoài transaction |
| Đánh dấu SENT trước send | Có thể ghi đã gửi dù message chưa được gửi | Ghi kết quả sau phản hồi SMTP |
| Coi SMTP accept là delivery/read | Đây là các mốc khác nhau | Dùng trạng thái mô tả chính xác |

## 19. Ví dụ kiến trúc hoàn chỉnh với outbox

Một cấu trúc service có thể như sau:

~~~text
HTTP request / application command
              |
              v
OrderApplicationService
       @Transactional
              |
              +-- Validate command
              +-- Update order
              +-- Build immutable mail snapshot
              +-- Insert mail_outbox row
              |
              v
            COMMIT
              |
              v
Outbox polling worker
              |
              +-- Claim pending event
              +-- Resolve template and locale
              +-- Render plain text / HTML
              +-- Build MimeMessage
              +-- JavaMailSender.send(...)
              +-- Save result or retry schedule
              |
              v
         SMTP provider
~~~

Các thành phần:

- **OrderApplicationService** quản lý transaction nghiệp vụ.
- **Mail snapshot** giữ dữ liệu email cần thiết tại thời điểm event.
- **Outbox repository** lưu ý định gửi và trạng thái.
- **Outbox worker** claim, retry và điều phối gửi.
- **Template renderer** tạo nội dung.
- **Mail delivery service** dựng MimeMessage và gọi JavaMailSender.
- **Monitoring** theo dõi backlog, lỗi, retry và thời gian xử lý.

Trong ứng dụng nhỏ, có thể bắt đầu bằng service gọi sau commit. Khi yêu cầu tin cậy tăng lên, có thể chuyển sang outbox mà không cần đưa logic SMTP vào domain service.

## 20. Ghi nhớ khi tách giao dịch dữ liệu khỏi giao dịch SMTP

**Transaction dữ liệu** và **giao dịch SMTP** là hai phạm vi độc lập. Spring transaction manager có thể commit hoặc rollback database, nhưng không thể thu hồi email đã được SMTP server chấp nhận. Gửi SMTP bên trong một phương thức @Transactional có thể khiến email được gửi trước khi database commit, giữ transaction lâu trong lúc chờ mạng và làm retry nghiệp vụ tạo email trùng.

Hãy để transaction nghiệp vụ cập nhật dữ liệu và tạo snapshot cần cho email, sau đó gửi sau commit. Có thể gọi mail service sau khi transactional service trả về, dùng **@TransactionalEventListener(AFTER_COMMIT)** hoặc kết hợp AFTER_COMMIT với **@Async**. Các cách này tách thời điểm và thread thực thi, nhưng event trong bộ nhớ có thể mất nếu process dừng sau commit.

Với email quan trọng, ghi ý định gửi vào **transactional outbox trong cùng transaction database**. Worker xử lý outbox ngoài transaction dữ liệu, lưu trạng thái, retry có backoff và theo dõi event ID ổn định. Outbox giúp phục hồi sau restart nhưng không bảo đảm SMTP exactly-once; worker có thể crash sau khi server chấp nhận message và trước khi ghi SENT, dẫn tới gửi lặp.

Hãy theo dõi riêng ba kết quả: **dữ liệu nghiệp vụ đã commit**, **SMTP/provider đã chấp nhận message**, và **email đã được chuyển tới hoặc đọc bởi người nhận**. Chúng không phải cùng một trạng thái. Khi ranh giới được thiết kế rõ, dữ liệu nghiệp vụ giữ được tính nhất quán và việc gửi email có thể được phục hồi, retry và đối soát độc lập.
