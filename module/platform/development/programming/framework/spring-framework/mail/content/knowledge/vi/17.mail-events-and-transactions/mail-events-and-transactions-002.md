# Rủi ro email đã gửi nhưng transaction bị rollback

Trong một ứng dụng Spring, nghiệp vụ có thể cập nhật database rồi gửi email xác nhận trong cùng một phương thức. Cách viết này trông tự nhiên, nhưng **transaction database không thể thu hồi một email mà SMTP server đã chấp nhận**.

Hãy xét một đơn hàng được xác nhận:

1. Ứng dụng mở transaction.
2. Cập nhật đơn hàng thành CONFIRMED.
3. Gửi email thông báo xác nhận.
4. Một thao tác database khác lỗi, hoặc lúc commit phát sinh lỗi.
5. Database rollback, nhưng email đã rời khỏi ứng dụng.

Người nhận có thể nhận thông báo “Đơn hàng đã được xác nhận” trong khi database vẫn ghi đơn hàng ở trạng thái cũ. Đây là sự không nhất quán giữa **trạng thái nghiệp vụ trong database** và **side effect bên ngoài**.

Spring quản lý transaction cho các resource tham gia transaction, thường là database. SMTP là một hệ thống độc lập. Một lần gọi JavaMailSender.send(...) không tự tham gia transaction database và không có cơ chế rollback email khi transaction thất bại.

Cách xử lý phổ biến là **chỉ phát lệnh gửi sau khi transaction nghiệp vụ commit thành công**. Với thông báo không được phép mất khi ứng dụng dừng đột ngột, nên lưu ý định gửi trong cùng transaction bằng **transactional outbox**, rồi để worker gửi sau commit. Dù dùng cách nào, cần xác định rõ khả năng gửi trùng, retry và trạng thái thực tế của message.

## 1. Transaction database không bao gồm SMTP

Một transaction database có thể gom nhiều thay đổi thành một đơn vị nguyên tử:

~~~text
BEGIN
  UPDATE orders SET status = 'CONFIRMED'
  INSERT INTO order_history (...)
  UPDATE inventory (...)
COMMIT
~~~

Nếu một thao tác thất bại trước commit, database có thể rollback những thay đổi thuộc transaction đó.

Gửi email lại là một side effect bên ngoài:

~~~text
Application
    |
    +----> Database transaction
    |
    +----> SMTP server
~~~

Database transaction manager không thể yêu cầu SMTP server xóa message đã nhận chỉ vì transaction database rollback. SMTP không tham gia cùng transaction cục bộ theo cách mà JDBC connection tham gia.

Ví dụ:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    mailService.sendConfirmation(order);
}
~~~

Phương thức này có hai loại thao tác:

- **Database work:** đọc và cập nhật đơn hàng.
- **External side effect:** gửi email qua SMTP.

Nếu SMTP chấp nhận email rồi transaction database thất bại khi commit, email không thể được rollback cùng database.

### 1.1. Thời điểm commit nằm sau phần thân phương thức

Trong mô hình Spring transaction thông thường dựa trên proxy, luồng xử lý có thể hiểu như sau:

~~~text
Caller
  |
  v
Spring transaction proxy
  |
  +-- Begin transaction
  |
  +-- Invoke method body
  |     |
  |     +-- Update database
  |     +-- Call JavaMailSender.send()
  |
  +-- Method returns
  |
  +-- Commit transaction
        |
        +-- Success
        |
        +-- Failure -> rollback if possible
~~~

Điểm quan trọng: khi code bên trong method gọi send, transaction database thường vẫn chưa commit. Việc phương thức chạy tới dòng cuối không đồng nghĩa commit đã thành công; transaction interceptor còn phải hoàn tất commit sau khi method trả về.

Do đó, gửi email ở cuối phương thức transactional vẫn có thể gửi trước commit.

### 1.2. Một ví dụ về thông báo sai trạng thái

Giả sử đơn hàng đang ở trạng thái PENDING:

~~~text
Trước transaction:
  orders.status = PENDING

Trong transaction:
  orders.status = CONFIRMED
  SMTP chấp nhận email "Đơn hàng đã xác nhận"

Khi commit:
  Database phát hiện lỗi và rollback

Sau transaction:
  orders.status = PENDING
  Email xác nhận vẫn có thể đến người nhận
~~~

Người nhận nhìn thấy thông tin khác với trạng thái thực tế. Họ có thể thanh toán tiếp, liên hệ hỗ trợ hoặc thực hiện một hành động dựa trên thông báo không đúng.

Với các email như xác nhận thanh toán, đặt chỗ, cấp quyền, hoàn tiền hoặc thay đổi mật khẩu, sự không nhất quán này có thể tạo hậu quả nghiệp vụ đáng kể.

## 2. Những thời điểm lỗi có thể xảy ra

Không chỉ có trường hợp một câu lệnh SQL ném exception. Transaction có thể thất bại ở nhiều thời điểm.

| Thời điểm | Điều có thể xảy ra | Email đã gửi có thể bị thu hồi không? |
| --- | --- | --- |
| Trước khi gửi | Validation hoặc cập nhật database lỗi | Chưa có email |
| Trong lúc gửi | SMTP timeout hoặc từ chối | Kết quả có thể là thất bại hoặc chưa xác định |
| SMTP đã chấp nhận, trước commit | Một câu lệnh tiếp theo lỗi | Không |
| Trong lúc commit | Constraint, deadlock, optimistic locking hoặc lỗi connection | Không |
| Sau commit | Listener hoặc worker gửi email gặp lỗi | Database vẫn đã commit |
| SMTP chấp nhận, worker crash trước khi ghi SENT | Worker có thể gửi lại | Không; có nguy cơ gửi trùng |

### 2.1. Lỗi sau khi SMTP đã chấp nhận

Một tình huống điển hình:

~~~text
T0  Transaction bắt đầu
T1  Cập nhật đơn hàng
T2  SMTP server chấp nhận message
T3  Một câu lệnh database lỗi
T4  Transaction rollback
T5  Người nhận vẫn có thể nhận email
~~~

Đây là trường hợp khó xử lý nhất trong code gửi mail trực tiếp bên trong transaction. Khi T2 xảy ra, side effect đã nằm ngoài quyền kiểm soát của database.

### 2.2. Commit có thể lỗi dù method body không ném exception

Một số lỗi chỉ được phát hiện khi database thực hiện commit, chẳng hạn constraint được kiểm tra ở thời điểm commit, lỗi kết nối hoặc transaction conflict. Code bên trong method có thể chạy hết, nhưng interceptor vẫn không commit thành công.

Vì vậy, không nên suy luận rằng “đã gọi send ở dòng cuối” nghĩa là transaction chắc chắn sẽ commit.

### 2.3. SMTP timeout không luôn có nghĩa server chưa nhận email

Một kết nối có thể bị ngắt sau khi SMTP server đã nhận dữ liệu nhưng trước khi ứng dụng nhận được phản hồi cuối cùng. Ứng dụng thấy timeout, nhưng kết quả thực tế có thể chưa xác định.

Nếu retry ngay, message có thể được chấp nhận lần thứ hai. Đây là một nguồn gửi trùng độc lập với rollback database.

### 2.4. SMTP accept không đồng nghĩa người nhận đã đọc thư

Cần phân biệt các mốc:

- Ứng dụng đã gọi send.
- SMTP server đã chấp nhận message.
- Provider đã chuyển tiếp message.
- Message đã tới mailbox.
- Email client hiển thị message.
- Người nhận đã đọc nội dung.

Một phản hồi gửi thành công từ JavaMailSender thường chỉ cho biết transport đã hoàn tất theo mức xác nhận mà SMTP server cung cấp. Nó không chứng minh người nhận đã đọc thư.

## 3. Vì sao gửi email trong @Transactional là rủi ro?

### 3.1. Database rollback không rollback side effect

Đây là vấn đề cốt lõi. Transaction manager có thể rollback database, nhưng không có thao tác tương đương để thu hồi email đã được SMTP server chấp nhận.

### 3.2. Transaction bị kéo dài bởi network I/O

SMTP có thể chậm do DNS, kết nối, TLS handshake, authentication, giới hạn tốc độ hoặc phản hồi của server. Trong lúc chờ, transaction database có thể vẫn giữ connection, lock và tài nguyên.

Ví dụ, một email mất 3 giây để gửi. Nếu một request tạo nhiều email tuần tự, transaction có thể mở lâu hơn đáng kể so với phần cập nhật dữ liệu cần thiết.

### 3.3. Lỗi gửi mail có thể làm rollback nghiệp vụ không cần thiết

Nếu send ném exception và exception đó thuộc loại khiến transaction rollback, một đơn hàng hợp lệ có thể bị rollback chỉ vì SMTP tạm thời không hoạt động.

Đôi khi email là điều kiện bắt buộc của một quy trình. Nhưng trong phần lớn hệ thống, việc xác nhận đơn hàng và việc chuyển thông báo qua SMTP là hai công việc có cách phục hồi khác nhau. Nên biểu diễn quan hệ đó rõ ràng thay vì để exception SMTP vô tình quyết định trạng thái database.

### 3.4. Retry toàn bộ transaction có thể tạo side effect lặp

Nếu ứng dụng retry phương thức transactional khi SMTP lỗi, lần thử đầu có thể đã gửi email nhưng transaction rollback. Lần thử tiếp theo lại gửi một email khác.

Nếu phương thức còn tạo bản ghi, phát hành mã hoặc gọi hệ thống ngoài khác, retry toàn bộ có thể lặp nhiều side effect.

### 3.5. Kết quả của nghiệp vụ trở nên khó hiểu

Một request có thể trả lỗi cho client vì transaction rollback dù email đã được gửi. Người dùng thử lại và nhận thêm một email. Hệ thống hỗ trợ cũng khó giải thích vì database không có bản ghi xác nhận nhưng mailbox lại có message.

## 4. Không gửi trực tiếp trước commit nếu email xác nhận thay đổi đã lưu

Nguyên tắc đơn giản:

**Nếu email khẳng định một thay đổi nghiệp vụ đã thành công, chỉ nên bắt đầu gửi sau khi transaction ghi thay đổi đó commit thành công.**

Có một số cách tổ chức:

1. Gọi service transactional từ một service điều phối, sau khi service trả về thành công mới gửi.
2. Phát Spring application event và xử lý bằng **@TransactionalEventListener(AFTER_COMMIT)**.
3. Kết hợp listener sau commit với **@Async** khi không muốn request chờ gửi.
4. Dùng **transactional outbox** khi ý định gửi phải được lưu bền vững và có thể phục hồi sau khi process dừng.

Mỗi cách giải quyết một phần yêu cầu khác nhau. AFTER_COMMIT xử lý thời điểm; @Async tách thread thực thi; outbox lưu ý định gửi cùng transaction database.

## 5. Cách đơn giản: gọi service transactional rồi mới gửi

Nếu email có thể gửi đồng bộ sau khi transaction hoàn tất và không cần một hàng đợi bền vững, hãy tách bean nghiệp vụ và bean điều phối.

Service cập nhật đơn hàng:

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

DTO:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String totalAmount
) {}
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

        // Transaction trong OrderService đã commit thành công
        // trước khi lời gọi qua proxy trả về đây.
        mailService.sendConfirmation(snapshot);
    }
}
~~~

Khi caller gọi **OrderService** qua Spring proxy, transaction được bắt đầu, cập nhật được thực hiện, rồi commit trước khi lời gọi transactional trả về bình thường. Nếu commit thất bại, facade không đi tiếp tới sendConfirmation.

### 5.1. Vì sao dùng hai bean?

Spring thường quản lý @Transactional qua proxy. Nếu một method gọi một method transactional khác trong cùng object bằng lời gọi nội bộ, lời gọi đó có thể không đi qua proxy; transaction annotation có thể không được áp dụng như người viết mong đợi.

Tách service transactional và facade thành hai bean làm ranh giới gọi rõ ràng.

### 5.2. Vì sao trả về DTO thay vì entity?

Sau khi transaction kết thúc, entity có thể detached khỏi persistence context. Nếu mail service truy cập quan hệ lazy, có thể phát sinh LazyInitializationException hoặc truy vấn ngoài ý muốn.

DTO snapshot chỉ chứa dữ liệu cần cho email:

- Recipient đã được xác định.
- Tên người nhận.
- Mã đơn hàng.
- Số tiền.
- Trạng thái hoặc thời điểm cần thông báo.

Renderer và mail service không cần biết JPA entity hoặc lazy relation.

### 5.3. Giới hạn của cách này

Cách gọi tuần tự có ưu điểm đơn giản, nhưng vẫn có một khoảng trống:

~~~text
1. Database commit thành công.
2. Process dừng trước khi facade gọi mailService.
3. Không có email nào được gửi.
~~~

Nó ngăn email được gửi trước một commit thất bại, nhưng không lưu bền vững ý định gửi. Nếu email có thể thử lại thủ công hoặc không quá quan trọng, điều này có thể chấp nhận được. Nếu không được phép mất thông báo, cần một cơ chế bền vững hơn.

## 6. Dùng @TransactionalEventListener(AFTER_COMMIT)

Spring hỗ trợ **@TransactionalEventListener** để xử lý application event theo một phase của transaction.

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
       +-- Publish OrderConfirmedEvent
       |
       v
Commit transaction
       |
       +-- Commit thành công
       |       |
       |       v
       |   AFTER_COMMIT listener
       |       |
       |       v
       |   Send email
       |
       +-- Rollback
               |
               v
           AFTER_COMMIT không chạy
~~~

Nếu transaction rollback, listener ở phase AFTER_COMMIT không được gọi. Nếu commit thành công, listener mới xử lý email.

### 6.1. Vì sao publish event trong transaction vẫn an toàn hơn gửi trực tiếp?

Lệnh publish event ở đây chỉ đăng ký một sự kiện cho listener được ràng buộc với transaction. Listener AFTER_COMMIT được gọi sau khi transaction commit thành công. Khi transaction rollback, listener không xử lý sự kiện ở phase này.

Điều khác biệt quan trọng là **publish event không phải gửi email**. Việc gửi chỉ xảy ra trong listener sau commit.

### 6.2. Các phase khác của TransactionalEventListener

Spring hỗ trợ các phase:

| Phase | Thời điểm |
| --- | --- |
| **BEFORE_COMMIT** | Trước khi transaction commit |
| **AFTER_COMMIT** | Sau khi commit thành công |
| **AFTER_ROLLBACK** | Sau khi rollback |
| **AFTER_COMPLETION** | Sau khi transaction hoàn tất, dù commit hay rollback |

Với email xác nhận thay đổi đã lưu thành công, **AFTER_COMMIT** thường là lựa chọn phù hợp.

**BEFORE_COMMIT** không giải quyết rủi ro đang nói tới. Listener vẫn chạy trước commit; transaction có thể thất bại sau khi email đã được gửi.

### 6.3. Không có transaction thì listener mặc định có thể không chạy

Transactional event listener mặc định yêu cầu có transaction đang hoạt động tại thời điểm event được publish. Nếu event được phát ngoài transaction, listener có thể không được gọi.

Tùy chọn **fallbackExecution = true** cho phép listener chạy cả khi không có transaction, nhưng cần dùng có chủ đích. Nếu bật tùy chọn này, listener có thể gửi email ngay cả khi event không gắn với transaction nghiệp vụ.

Không bật fallback chỉ để che một lỗi thiết kế khiến event được publish sai vị trí.

### 6.4. AFTER_COMMIT không tự làm event bền vững

Spring application event thông thường được phát trong process. Một tình huống vẫn có thể xảy ra:

~~~text
1. Database commit thành công.
2. Process crash ngay sau commit.
3. Listener chưa xử lý event.
4. Event trong bộ nhớ mất khi process dừng.
5. Email không được gửi.
~~~

AFTER_COMMIT bảo đảm thời điểm gọi listener trong vòng đời transaction; nó không tự lưu event vào database, không tạo queue durable và không tự retry sau restart.

## 7. Kết hợp AFTER_COMMIT với @Async

Nếu không muốn request người dùng chờ SMTP, có thể xử lý listener bất đồng bộ.

Bật async:

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

Các giá trị trên chỉ là ví dụ. Cần cấu hình theo lưu lượng email, giới hạn SMTP provider và tài nguyên ứng dụng.

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

Luồng:

~~~text
Request
   |
   v
@Transactional service
   |
   +-- Update database
   +-- Publish event
   +-- Commit
   |
   v
AFTER_COMMIT listener
   |
   v
Submit task to executor
   |
   v
Worker thread
   |
   +-- Render template
   +-- Build MimeMessage
   +-- Send SMTP
   |
   v
End
~~~

### 7.1. @Async giải quyết điều gì?

- Tách thời gian render và gửi khỏi thread xử lý request.
- Không giữ transaction nghiệp vụ mở trong lúc chờ SMTP.
- Cho phép giới hạn số tác vụ gửi đồng thời bằng executor.
- Lỗi trong async task không thể rollback transaction đã commit.

### 7.2. @Async không tự retry và không bảo đảm không mất task

Executor trong process có queue hữu hạn. Nếu queue đầy, task có thể bị từ chối theo chính sách executor. Nếu ứng dụng dừng đột ngột, task đang chờ hoặc đang chạy có thể không hoàn tất.

Do đó:

- **AFTER_COMMIT** xử lý thời điểm.
- **@Async** xử lý cách thực thi.
- **Transactional outbox** xử lý việc lưu bền vững ý định gửi.

Ba cơ chế này không thay thế nhau.

### 7.3. Xử lý exception trong async listener

Một phương thức async trả về void không thể đưa exception trở lại request đã kết thúc. Cần ghi nhận lỗi ở listener hoặc cơ chế xử lý async phù hợp:

~~~java
@Async("mailExecutor")
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
)
public void onOrderConfirmed(OrderConfirmedEvent event) {
    try {
        mailService.sendConfirmation(event.mailData());
    } catch (Exception ex) {
        log.error(
                "Cannot send confirmation for order {}",
                event.mailData().orderNumber(),
                ex
        );
        // Ghi nhận trạng thái lỗi hoặc chuyển sang cơ chế retry.
    }
}
~~~

Đây là minh họa về xử lý exception. Log cần tránh ghi dữ liệu cá nhân, nội dung attachment hoặc credential. Với email quan trọng, chỉ log lỗi là chưa đủ; cần trạng thái bền vững để có thể tiếp tục xử lý.

### 7.4. Không truyền JPA entity sang async worker

Worker chạy trên thread khác và không kế thừa persistence context của transaction caller. Hãy truyền DTO snapshot hoặc một event payload có thể serialize.

Nếu chỉ truyền order ID, worker cần mở transaction riêng để đọc dữ liệu. Khi đó phải quyết định email cần snapshot tại thời điểm xác nhận hay trạng thái mới nhất tại thời điểm worker chạy.

## 8. Transactional outbox: lưu ý định gửi cùng transaction

Khi không được phép mất ý định gửi sau khi database commit, **transactional outbox** là một giải pháp phổ biến.

Thay vì chỉ publish một event trong bộ nhớ, ứng dụng ghi một bản ghi outbox trong cùng transaction với thay đổi nghiệp vụ.

Ví dụ:

~~~text
orders
  id = 1001
  status = CONFIRMED

mail_outbox
  id = 9001
  event_type = ORDER_CONFIRMED
  payload = { ...mail snapshot... }
  status = PENDING
~~~

Hai thay đổi được commit nguyên tử:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE id = 1001;

INSERT INTO mail_outbox (
    id,
    event_type,
    payload,
    status,
    created_at
)
VALUES (
    '9001',
    'ORDER_CONFIRMED',
    '{...}',
    'PENDING',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Nếu transaction rollback, cả thay đổi đơn hàng và bản ghi outbox đều rollback. Nếu commit thành công, worker có thể tìm thấy bản ghi PENDING sau khi ứng dụng khởi động lại.

### 8.1. Vì sao outbox giải quyết được khoảng trống sau commit?

So sánh:

~~~text
AFTER_COMMIT event in memory:
  Database commit
       |
       +-- Process crash
       |
       +-- Event có thể bị mất
~~~

~~~text
Transactional outbox:
  Database transaction
       |
       +-- Update business data
       +-- Insert outbox row
       |
       v
     COMMIT
       |
       v
  Outbox row vẫn nằm trong database
       |
       v
  Worker xử lý khi sẵn sàng
~~~

Ý định gửi được lưu cùng transaction. Worker không cần dựa vào một event chỉ tồn tại trong bộ nhớ của process.

### 8.2. Schema outbox minh họa

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

Schema thực tế có thể thêm:

- Recipient hoặc reference tới recipient.
- Template key và template version.
- Locale.
- Correlation ID.
- Lease owner và lease expiry.
- Thời điểm xử lý gần nhất.
- Loại lỗi đã phân loại.
- Số lần thử tối đa.

Nếu payload chứa dữ liệu cá nhân, cần chính sách phân quyền đọc, mã hóa khi lưu nếu phù hợp, thời hạn lưu và xóa dữ liệu.

### 8.3. Ghi outbox trong service transactional

Ví dụ:

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

Trong transaction này không gọi SMTP. Nếu commit thành công, order và outbox row cùng tồn tại. Nếu rollback, cả hai không được commit.

### 8.4. Worker đọc và gửi

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

Đây là luồng khái niệm, chưa phải implementation hoàn chỉnh. Trong ứng dụng thực tế, **claimPendingBatch** cần cơ chế khóa hoặc lease để nhiều worker không cùng xử lý một event. Việc claim và cập nhật trạng thái phải được quản lý bằng transaction phù hợp.

### 8.5. Không giữ transaction database trong lúc gửi SMTP

Một worker có thể:

1. Mở transaction ngắn để claim event và ghi lease.
2. Commit claim.
3. Đọc payload đã claim.
4. Render và gửi SMTP ngoài transaction claim.
5. Mở transaction khác để đánh dấu kết quả.

Cách này tránh giữ lock database trong thời gian network I/O. Nếu worker chết giữa bước gửi và bước cập nhật trạng thái, event có thể được claim lại sau khi lease hết hạn; đó là lý do cần thiết kế idempotency và xử lý gửi trùng.

## 9. Outbox không bảo đảm exactly-once email

Transactional outbox giúp lưu bền vững ý định gửi và cho phép worker thử lại. Nhưng SMTP không tham gia cùng transaction database, vì vậy vẫn có khoảng trống:

~~~text
1. Worker lấy event PENDING.
2. SMTP server chấp nhận email.
3. Worker crash trước khi đánh dấu event SENT.
4. Lease hết hạn.
5. Worker khác lấy lại event.
6. Email được gửi lần nữa.
~~~

Kết quả có thể là người nhận nhận hai email.

Đây là giới hạn quan trọng: outbox thường cung cấp **at-least-once processing** cho tác vụ gửi, chứ không bảo đảm một email xuất hiện chính xác một lần trong mailbox.

### 9.1. Event ID ổn định

Mỗi ý định gửi nên có một ID ổn định. ID này được dùng trong:

- Bản ghi outbox.
- Log.
- Correlation ID.
- Lịch sử retry.
- Metadata phục vụ đối soát.

Không tạo ID mới cho mỗi lần retry cùng một ý định gửi. ID ổn định giúp nhận diện các lần xử lý thuộc cùng một tác vụ.

### 9.2. Message-ID không phải idempotency guarantee

Email có header Message-ID. Việc dùng một Message-ID ổn định có thể hữu ích khi tra cứu hoặc đối soát, nhưng không buộc mọi SMTP server hay email client loại bỏ message trùng.

Nếu SMTP provider hỗ trợ idempotency key theo API riêng, có thể sử dụng theo hợp đồng của provider. SMTP thuần không cung cấp một cơ chế exactly-once tổng quát.

### 9.3. Thiết kế nội dung chịu được gửi lặp

Với email xác nhận, có thể giảm ảnh hưởng của gửi trùng bằng cách:

- Dùng mã đơn hàng hoặc mã sự kiện ổn định.
- Tránh tạo một mã xác nhận mới ở mỗi lần retry.
- Không khiến người nhận hiểu mỗi email lặp là một giao dịch mới.
- Lưu trạng thái và lịch sử gửi để hỗ trợ xử lý.
- Phân biệt retry của cùng một event với một event nghiệp vụ mới.

Đối với email có link một lần hoặc mã xác thực, cần đặc biệt cẩn trọng: retry không được phát hành các token không nhất quán hoặc vô tình vô hiệu hóa token đang có hiệu lực.

## 10. Snapshot dữ liệu hay chỉ lưu ID trong outbox?

Worker có thể nhận đầy đủ dữ liệu email hoặc chỉ nhận ID để tải lại dữ liệu.

| Cách lưu | Ưu điểm | Hạn chế |
| --- | --- | --- |
| **Snapshot DTO** | Nội dung phản ánh thời điểm nghiệp vụ; không cần lazy entity | Payload lớn hơn và có thể chứa dữ liệu cá nhân |
| **Chỉ lưu business ID** | Payload nhỏ; worker đọc trạng thái mới nhất | Dữ liệu có thể thay đổi hoặc bị xóa trước khi worker chạy |
| **Snapshot + template version** | Có thể tái tạo nội dung theo phiên bản đã chọn | Cần quản lý phiên bản template và retention |

### 10.1. Snapshot phù hợp với email xác nhận sự kiện

Ví dụ đơn hàng được xác nhận lúc 10:00 với tổng tiền 500.000 đồng. Lúc 10:05, dữ liệu khách hàng hoặc đơn hàng thay đổi.

Nếu email mô tả chính sự kiện xác nhận lúc 10:00, snapshot giúp giữ số tiền, tên và thông tin tại thời điểm đó.

### 10.2. Reload phù hợp khi cần trạng thái mới nhất

Với email nhắc nhở hoặc tổng hợp, có thể cần dữ liệu tại thời điểm worker chạy. Khi đó worker tải lại theo ID, nhưng cần xác định rõ nếu bản ghi không còn tồn tại hoặc trạng thái đã đổi thì tác vụ sẽ được xử lý thế nào.

### 10.3. Không lưu entity JPA trong payload

Không serialize trực tiếp toàn bộ JPA entity vào event/outbox. Entity có thể chứa quan hệ vòng, lazy proxy và dữ liệu không cần thiết. Hãy tạo DTO có schema rõ ràng, chỉ chứa thông tin được phép dùng cho email.

## 11. Trường hợp email gửi thành công nhưng database rollback do exception

Cần hiểu quy tắc rollback của Spring.

Theo mặc định, trong cấu hình transaction phổ biến, Spring rollback khi method transactional kết thúc bằng **RuntimeException** hoặc **Error**. Checked exception không tự động kích hoạt rollback theo cùng quy tắc mặc định, trừ khi cấu hình rollback rule phù hợp.

Ví dụ:

~~~java
@Transactional
public void confirmOrder(UUID orderId) throws MessagingException {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    mailService.sendConfirmation(order);
}
~~~

Nếu **MessagingException** là checked exception và được ném ra, transaction không nhất thiết rollback theo mặc định. Nếu exception được wrap thành RuntimeException hoặc có rollbackFor tương ứng, transaction có thể rollback.

Điều này ảnh hưởng tới tình huống **gửi mail thất bại**. Nhưng rủi ro email đã gửi rồi transaction rollback vẫn tồn tại nếu một lỗi runtime hoặc lỗi commit xảy ra sau khi SMTP đã chấp nhận message.

### 11.1. Không dùng rollback rule để giải quyết side effect

Có thể cấu hình:

~~~java
@Transactional(rollbackFor = Exception.class)
~~~

Điều này thay đổi quy tắc rollback cho exception, nhưng không làm SMTP trở thành một phần của database transaction. Nếu email đã được gửi rồi exception khiến rollback, email vẫn không thể thu hồi.

Rollback rule chỉ quyết định database transaction có rollback hay không; nó không tạo khả năng rollback external side effect.

### 11.2. Bắt exception SMTP rồi tiếp tục không giải quyết mất thông báo

Ví dụ:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    log.warn("Email failed", ex);
}
~~~

Cách này có thể giúp transaction nghiệp vụ tiếp tục, nhưng nếu không lưu trạng thái hoặc tạo tác vụ retry, email thất bại có thể bị mất vĩnh viễn.

Nếu email là tùy chọn, ghi nhận trạng thái lỗi có thể đủ. Nếu email là nghĩa vụ của nghiệp vụ, cần lưu ý định gửi bền vững.

## 12. Transaction synchronization và TransactionSynchronizationManager

Ngoài **@TransactionalEventListener**, Spring có API transaction synchronization để đăng ký callback theo vòng đời transaction.

Ví dụ minh họa:

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

Callback **afterCommit()** được gọi sau khi transaction commit thành công. Nếu transaction rollback, callback sau commit không được thực hiện.

Cách này cho phép đăng ký hành động trực tiếp theo transaction, nhưng thường ít tường minh về mặt nghiệp vụ hơn một event listener. Cần bảo đảm đang có transaction synchronization hoạt động trước khi đăng ký; nếu không, code có thể cần xử lý trường hợp không có transaction.

### 12.1. Hạn chế tương tự AFTER_COMMIT event

Transaction synchronization callback vẫn nằm trong process. Nếu process crash sau commit trước callback, email có thể không được gửi. Nó không thay thế outbox nếu cần durability.

### 12.2. Không gọi SMTP trong beforeCommit

Đăng ký callback **beforeCommit()** rồi gửi email vẫn tạo cùng rủi ro: commit có thể thất bại sau callback. Nếu mục tiêu là không gửi trước khi transaction thành công, phải dùng afterCommit hoặc một worker đọc outbox sau commit.

## 13. Cẩn thận với thao tác database trong AFTER_COMMIT listener

Sau khi transaction commit, Spring có thể vẫn giữ một số resource transaction gắn với thread trong quá trình callback hoàn tất. Tài liệu Spring lưu ý rằng thao tác truy cập dữ liệu ở phase AFTER_COMMIT có thể vẫn nhìn thấy resource nhưng những thay đổi mới không được commit vào transaction đã hoàn tất.

Nếu listener cần ghi một bản ghi trạng thái riêng sau commit, hãy dùng một transaction mới có chủ đích, chẳng hạn **Propagation.REQUIRES_NEW** trên một bean riêng.

Ví dụ:

~~~java
@Service
public class MailStatusService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(UUID eventId, String reason) {
        // Lưu trạng thái lỗi trong transaction mới.
    }
}
~~~

Phương thức cần được gọi qua Spring proxy để propagation có hiệu lực trong mô hình proxy thông thường. Không nên dùng REQUIRES_NEW một cách máy móc; chỉ cần khi listener thực sự ghi dữ liệu sau transaction gốc và muốn commit độc lập.

Với outbox, worker thường quản lý transaction claim và transaction cập nhật trạng thái riêng, nên ranh giới này được thể hiện rõ hơn.

## 14. Phân biệt lỗi nghiệp vụ với lỗi gửi mail

Không phải mọi email đều có cùng mức độ quan trọng.

| Loại email | Ví dụ | Cách xử lý có thể phù hợp |
| --- | --- | --- |
| Thông báo tiện ích | Báo có bài viết mới | Có thể gửi best-effort sau commit |
| Email xác nhận giao dịch | Xác nhận đơn hàng hoặc thanh toán | Cần lưu và theo dõi ý định gửi |
| Email bảo mật | Cảnh báo đăng nhập, đổi mật khẩu | Cần kiểm soát thời điểm, nội dung và retry chặt chẽ |
| Email chứa chứng từ | Hóa đơn hoặc biên nhận | Cần snapshot/version và lịch sử gửi |
| Bản tin hàng loạt | Newsletter | Queue, giới hạn tốc độ và xử lý unsubscribe |

Với email tiện ích, một listener AFTER_COMMIT có thể đủ. Với email xác nhận giao dịch hoặc chứng từ, transactional outbox thường phù hợp hơn vì có thể phục hồi khi ứng dụng dừng.

### 14.1. Email không nên quyết định ngược trạng thái nghiệp vụ một cách vô thức

Ví dụ, SMTP tạm ngừng không nhất thiết có nghĩa đơn hàng chưa được xác nhận. Có thể đơn hàng đã commit và trạng thái thông báo là PENDING.

Nếu nghiệp vụ thật sự yêu cầu chỉ hoàn tất khi có xác nhận từ một hệ thống bên ngoài, cần mô hình hóa quy trình đó bằng trạng thái và bước phối hợp rõ ràng. Không nên dựa vào việc gọi SMTP bên trong transaction để giả lập một giao dịch phân tán nguyên tử.

## 15. Retry cần có trạng thái và backoff

Nếu gửi thất bại, worker có thể retry. Không nên retry liên tục trong vòng lặp ngắn vì có thể làm SMTP provider quá tải hoặc tạo nhiều message trùng.

Một mô hình trạng thái:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP accepted --> SENT_TO_PROVIDER
   |
   +-- temporary error --> RETRY_WAIT
   |                         |
   |                         v
   |                      PROCESSING
   |
   +-- permanent error --> FAILED
~~~

Có thể sử dụng exponential backoff:

~~~text
Lần 1: chờ ngắn
Lần 2: chờ lâu hơn
Lần 3: chờ lâu hơn nữa
...
Đạt giới hạn: chuyển FAILED hoặc dead-letter
~~~

Cần thêm jitter để nhiều worker không retry đồng loạt cùng một thời điểm. Thời gian cụ thể phụ thuộc loại lỗi, chính sách provider và SLA của email.

### 15.1. Phân loại lỗi trước khi retry

| Nhóm lỗi | Ví dụ | Hành động |
| --- | --- | --- |
| Tạm thời | SMTP 4xx, timeout có thể retry | Backoff và thử lại theo giới hạn |
| Vĩnh viễn | Recipient không hợp lệ, policy từ chối cố định | Đánh dấu lỗi, không retry vô hạn |
| Không xác định | Mất kết nối sau khi có thể SMTP đã nhận DATA | Xử lý thận trọng vì có thể gửi trùng |
| Lỗi tạo message | Template lỗi, attachment không tồn tại | Sửa dữ liệu hoặc template trước khi retry |

Không phải mọi exception MailException đều có cùng tính chất. Cần xem nguyên nhân gốc và phản hồi SMTP nếu có.

### 15.2. Không đánh dấu SENT trước khi send

Nếu worker ghi SENT trước khi gọi SMTP rồi process crash, email có thể không được gửi nhưng database ghi đã gửi.

Nếu gửi trước rồi mới ghi SENT, crash ở khoảng giữa có thể gây gửi trùng.

Không có thứ tự ghi database và gọi SMTP nào loại bỏ hoàn toàn khoảng trống này khi hai hệ thống không tham gia cùng một transaction phân tán. Hãy chọn semantics phù hợp, lưu trạng thái rõ ràng và thiết kế duplicate handling.

## 16. Idempotency ở tầng nghiệp vụ

**Idempotency** có nghĩa xử lý lặp cùng một ý định không tạo ra hiệu ứng nghiệp vụ mới ngoài dự kiến.

Ví dụ, một event xác nhận đơn hàng có ID ổn định:

~~~text
eventId = 8d...
type = ORDER_CONFIRMED
orderId = 1001
~~~

Worker có thể lưu event ID trong outbox và lịch sử xử lý. Nếu nhận lại cùng event, nó có thể kiểm tra tác vụ đã được xử lý đến đâu.

Tuy nhiên, nếu SMTP đã chấp nhận email mà worker chưa kịp ghi nhận, database không biết chắc server đã nhận hay chưa. Vì thế idempotency ở database giúp kiểm soát việc claim và xử lý event, nhưng không tự biến SMTP thành exactly-once.

### 16.1. Tạo event duy nhất cho một chuyển trạng thái

Không nên phát event ORDER_CONFIRMED mỗi lần một request retry chạy qua nếu đơn hàng đã được xác nhận từ trước. Có thể dùng transition hợp lệ hoặc unique constraint trên event key để ngăn tạo nhiều outbox row cho cùng một lần chuyển trạng thái.

Ví dụ khóa nghiệp vụ:

~~~text
ORDER_CONFIRMED:order-1001:version-3
~~~

Khóa phải phản ánh đúng một lần chuyển trạng thái. Nếu đơn hàng có thể được xác nhận lại theo một quy trình mới, cần version hoặc event ID khác.

### 16.2. Idempotency không có nghĩa bỏ qua mọi email giống nội dung

Hai email có cùng subject và body vẫn có thể là hai sự kiện hợp lệ khác nhau. Định danh idempotency nên gắn với **ý định nghiệp vụ**, không chỉ hash của nội dung email.

## 17. Những lựa chọn không giải quyết được vấn đề

### 17.1. Đặt lệnh send ở dòng cuối method

Dù send là câu lệnh cuối, transaction vẫn commit sau khi method body kết thúc. Commit có thể thất bại.

### 17.2. Bắt exception rồi rollback thủ công

Rollback database không thu hồi email đã được SMTP chấp nhận. Cũng không nên cố gọi một email thứ hai để “đính chính” cho mọi exception kỹ thuật; cần xác định trạng thái nghiệp vụ thực tế trước.

### 17.3. Dùng @Async ngay bên trong transaction

Nếu chỉ đánh dấu một method gửi mail là @Async và gọi nó trong transaction, task có thể bắt đầu trước khi transaction commit. Worker có thể gửi email trong khi transaction sau đó rollback.

**@Async không tự đợi transaction commit.** Nếu dùng async cho thông báo sau commit, hãy kết hợp với AFTER_COMMIT hoặc để worker đọc outbox.

### 17.4. Dùng @Transactional(propagation = REQUIRES_NEW) cho mail service

REQUIRES_NEW tạo hoặc dùng một transaction database riêng cho các thao tác database của method. Nó không làm SMTP tham gia transaction đó và không thể rollback email.

Đặt mail service trong REQUIRES_NEW không giải quyết việc email đã được gửi nhưng transaction nghiệp vụ bên ngoài rollback. Ranh giới cần quan tâm là thời điểm gửi so với commit nghiệp vụ.

### 17.5. Dùng @TransactionalEventListener(BEFORE_COMMIT)

BEFORE_COMMIT vẫn chạy trước khi database xác nhận commit. Nếu listener gửi mail, lỗi commit sau đó vẫn có thể khiến email thông báo một thay đổi chưa được lưu.

### 17.6. Giả định SMTP có exactly-once

SMTP không cung cấp một giao dịch nguyên tử chung với database của ứng dụng. Hãy thiết kế để chịu được retry và kết quả không xác định.

## 18. Kiểm thử rủi ro rollback và cách xử lý

Các tình huống kiểm thử quan trọng:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Transaction commit thành công | Email được phép xử lý sau commit |
| Transaction rollback trước commit | AFTER_COMMIT listener không gửi email |
| SMTP lỗi sau commit | Database vẫn giữ trạng thái nghiệp vụ đã commit; lỗi gửi được ghi nhận |
| Process dừng sau commit trước listener in-memory | Có thể mất event nếu không dùng outbox |
| Outbox row được commit, worker dừng | Row vẫn tồn tại để worker xử lý sau restart |
| SMTP accept rồi worker crash trước mark SENT | Có thể retry và gửi trùng; cần đối soát |
| Worker retry gặp lỗi vĩnh viễn | Event chuyển trạng thái FAILED/dead-letter theo policy |
| Hai worker cùng chạy | Cơ chế claim/lease ngăn xử lý đồng thời cùng event |

### 18.1. Kiểm tra AFTER_COMMIT

Một integration test có thể:

1. Bắt đầu transaction.
2. Thực hiện cập nhật nghiệp vụ và publish event.
3. Commit.
4. Xác nhận listener được gọi.

Một test khác rollback transaction và xác nhận listener AFTER_COMMIT không được gọi.

Cần dùng transaction test phù hợp; nếu test framework tự rollback transaction sau test, phase AFTER_COMMIT có thể không chạy như một transaction commit thực sự. Hãy chủ động commit trong kịch bản test cần kiểm tra listener.

### 18.2. Kiểm tra outbox

Có thể kiểm tra:

- Cập nhật nghiệp vụ và insert outbox cùng commit.
- Rollback làm cả hai thay đổi không tồn tại.
- Worker claim đúng trạng thái PENDING.
- Retry cập nhật attempts và next_attempt_at.
- Worker restart tiếp tục xử lý event còn pending.
- Event đã SENT không bị claim như tác vụ mới.

### 18.3. Dùng SMTP capture server

Một SMTP capture server trong môi trường test cho phép quan sát message mà không gửi tới người dùng thật. Có thể kiểm tra số message được nhận, recipient, subject, body và attachment.

Để kiểm tra duplicate window, có thể mô phỏng worker crash sau khi SMTP chấp nhận message nhưng trước khi cập nhật outbox. Test này giúp thấy rõ vì sao outbox không bảo đảm exactly-once delivery.

## 19. Kiến trúc gợi ý cho email giao dịch

Với email xác nhận quan trọng, một luồng có thể tổ chức:

~~~text
HTTP request / command
          |
          v
OrderApplicationService
    @Transactional
          |
          +-- Validate command
          +-- Update order
          +-- Create immutable mail snapshot
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
          +-- Update status or retry schedule
          |
          v
       SMTP provider
~~~

Trách nhiệm:

- **OrderApplicationService:** quản lý thay đổi nghiệp vụ.
- **Mail snapshot:** giữ dữ liệu tại thời điểm event.
- **Outbox repository:** lưu ý định gửi và trạng thái.
- **Worker:** claim, retry và điều phối việc gửi.
- **Template renderer:** tạo subject và body.
- **Mail delivery service:** dựng MimeMessage và gọi JavaMailSender.
- **Monitoring:** theo dõi pending, retry, failed và thời gian xử lý.

Với ứng dụng nhỏ, có thể bắt đầu bằng service gọi sau commit hoặc AFTER_COMMIT listener. Khi yêu cầu durability tăng, outbox cho phép worker tiếp tục xử lý sau khi ứng dụng restart.

## 20. Chọn giải pháp theo mức độ quan trọng của email

| Yêu cầu | Giải pháp có thể phù hợp | Giới hạn cần nhớ |
| --- | --- | --- |
| Email tiện ích, có thể bỏ lỡ trong trường hợp hiếm | Gửi sau khi transactional service trả về | Process có thể dừng trước khi send |
| Chỉ cần không gửi trước commit | AFTER_COMMIT listener | Event in-memory không durable |
| Không muốn request chờ SMTP | AFTER_COMMIT + @Async | Task có thể mất khi process dừng |
| Cần phục hồi tác vụ sau restart | Transactional outbox | Có thể gửi trùng ở failure window |
| Cần retry và theo dõi từng lần gửi | Outbox/queue cùng trạng thái | Cần quản lý lease, backoff và dead-letter |
| Nội dung phải phản ánh dữ liệu tại thời điểm giao dịch | Snapshot DTO trong transaction | Payload cần được bảo vệ và quản lý retention |
| Email có thể dùng dữ liệu mới nhất | Worker reload theo ID | Nội dung có thể thay đổi sau thời điểm event |

Không cần dùng outbox cho mọi email. Nhưng nếu email là một phần quan trọng của quy trình nghiệp vụ và không được phép mất ý định gửi, chỉ dùng event trong bộ nhớ thường chưa đủ.

## 21. Câu hỏi thường gặp

**1. Vì sao email vẫn gửi khi transaction rollback?**

Vì SMTP là hệ thống bên ngoài và không tham gia transaction database. Khi SMTP server đã chấp nhận message, rollback database không thể thu hồi message đó.

**2. Đặt send ở cuối method @Transactional có an toàn không?**

Không bảo đảm. Transaction thường commit sau khi method body trả về qua Spring proxy. Commit vẫn có thể thất bại sau lời gọi send.

**3. @TransactionalEventListener(AFTER_COMMIT) có ngăn email gửi trước commit không?**

Có, với event được publish trong transaction và listener hoạt động theo phase AFTER_COMMIT. Nếu transaction rollback, listener không chạy ở phase đó.

**4. AFTER_COMMIT có bảo đảm email luôn được gửi không?**

Không. Process có thể dừng sau commit trước khi listener xử lý. Listener in-memory không tự lưu bền vững event.

**5. @Async có tự đợi transaction commit không?**

Không. @Async chỉ chuyển công việc sang executor. Muốn chạy sau commit, cần kết hợp phase AFTER_COMMIT hoặc một worker đọc outbox.

**6. Transactional outbox giải quyết điều gì?**

Nó lưu bản ghi ý định gửi cùng transaction với thay đổi nghiệp vụ. Nếu commit thành công, worker có thể tiếp tục xử lý sau khi ứng dụng restart.

**7. Outbox có bảo đảm chỉ gửi đúng một email không?**

Không. Worker có thể crash sau khi SMTP chấp nhận email nhưng trước khi ghi trạng thái SENT. Retry có thể gửi trùng.

**8. Có thể rollback một email đã được gửi không?**

Không thể thu hồi email khỏi SMTP server hoặc mailbox bằng rollback database. Nếu cần sửa thông tin, ứng dụng có thể gửi một thông báo đính chính mới sau khi xác định trạng thái nghiệp vụ.

**9. REQUIRES_NEW có giải quyết vấn đề không?**

Không. REQUIRES_NEW tạo transaction database riêng cho thao tác database. SMTP vẫn là side effect bên ngoài và không thể rollback cùng transaction đó.

**10. Nếu SMTP lỗi thì đơn hàng có nên rollback không?**

Tùy nghiệp vụ. Thông thường trạng thái đơn hàng và việc gửi thông báo được quản lý riêng; email có thể ở trạng thái PENDING hoặc FAILED để retry. Nếu email thực sự là điều kiện của quy trình, cần mô hình hóa bước đó rõ ràng thay vì phụ thuộc ngẫu nhiên vào exception SMTP.

**11. Có nên truyền JPA entity cho AFTER_COMMIT listener không?**

Nên truyền DTO snapshot hoặc event payload có thể serialize. Entity có thể detached và quan hệ lazy không còn truy cập được.

**12. SMTP timeout có chắc chắn email chưa được gửi không?**

Không. Server có thể đã chấp nhận message nhưng phản hồi không tới ứng dụng. Retry có thể tạo duplicate.

**13. BEFORE_COMMIT có thể dùng để gửi mail không?**

Không phù hợp khi email khẳng định transaction đã thành công. Commit vẫn có thể thất bại sau callback.

**14. Làm thế nào để giảm email trùng?**

Dùng event ID ổn định, kiểm soát việc tạo event, trạng thái outbox, lease và idempotency ở tầng nghiệp vụ. Nếu provider hỗ trợ idempotency key, dùng theo hợp đồng của provider. SMTP thuần không bảo đảm exactly-once.

## 22. Ghi nhớ về rủi ro email đã gửi nhưng transaction bị rollback

**Transaction database chỉ rollback được những thay đổi thuộc resource mà nó quản lý.** Email gửi qua SMTP là side effect bên ngoài. Nếu SMTP server đã chấp nhận message trước khi transaction commit thất bại, email vẫn có thể đến người nhận dù database quay về trạng thái cũ.

Không gửi email xác nhận thành công trực tiếp bên trong transaction nghiệp vụ nếu message chỉ đúng sau khi commit. Có thể gọi mail service sau khi transactional service trả về, dùng **@TransactionalEventListener(AFTER_COMMIT)** hoặc kết hợp AFTER_COMMIT với **@Async** khi cần tách thời gian gửi khỏi request. Các cách này xử lý thời điểm và cách thực thi, nhưng event trong bộ nhớ vẫn có thể mất nếu process dừng sau commit.

Với email quan trọng, hãy lưu ý định gửi trong cùng transaction bằng **transactional outbox**, rồi để worker render và gửi sau commit. Outbox giúp phục hồi tác vụ sau restart và hỗ trợ retry, nhưng không bảo đảm exactly-once vì worker có thể dừng sau khi SMTP chấp nhận message mà trước khi ghi trạng thái SENT. Cần event ID ổn định, trạng thái rõ ràng, backoff, xử lý duplicate và giám sát lỗi.

Hãy tách ba kết quả: **nghiệp vụ đã commit**, **SMTP đã chấp nhận message**, và **người nhận đã nhận hoặc đọc email**. Chúng là các mốc khác nhau. Thiết kế đúng ranh giới transaction giúp thông báo phản ánh trạng thái nghiệp vụ chính xác và giúp hệ thống phục hồi có kiểm soát khi SMTP hoặc process gặp sự cố.
