# Tránh gọi hệ thống ngoài trong lúc giữ giao dịch cơ sở dữ liệu

Trong ứng dụng Java dùng JPA, một transaction cơ sở dữ liệu thường bao quanh các thao tác như tạo đơn hàng, cập nhật tồn kho, ghi thanh toán hoặc thay đổi trạng thái nghiệp vụ. Transaction giúp những thay đổi thuộc **cùng database transaction** được commit hoặc rollback theo nguyên tắc nhất quán. Nhưng nó không tự bảo đảm các thao tác bên ngoài database, chẳng hạn gọi HTTP API, gửi email, publish message hay yêu cầu một cổng thanh toán, sẽ thành công hoặc rollback cùng giao dịch.

Một lỗi thiết kế phổ biến là viết:

```java
@Transactional
public void placeOrder(CheckoutRequest request) {
    Order order = createOrderInDatabase(request);
    paymentGateway.charge(request.paymentToken(), order.getTotal());
    emailService.sendConfirmation(order);
}
```

Nếu `paymentGateway.charge(...)` chờ mạng trong vài giây, transaction database có thể vẫn mở trong suốt thời gian đó. Nếu email đã gửi nhưng transaction cuối cùng rollback, người nhận có thông báo về một đơn hàng không tồn tại. Nếu kết nối mạng timeout sau khi phía thanh toán **đã trừ tiền**, ứng dụng cũng không thể biết chắc kết quả chỉ qua exception.

**Nguyên tắc chính:** Giữ giao dịch database **ngắn và tập trung vào những thay đổi database cần tính nguyên tử**. Không đặt lời gọi dịch vụ ngoài hoặc công việc có độ trễ không kiểm soát trong transaction đang giữ lock, snapshot, connection hay trạng thái JPA nếu không có lý do và cơ chế đặc biệt đủ mạnh.

Bài học thuộc chương **Giao dịch** trong module *Data Persistence Relational Access ORM JPA*, giải thích lý do, hậu quả, những thiết kế thay thế và cách triển khai bằng JPA/Spring, transactional outbox, xử lý idempotent và saga.

## 1. Xác định ranh giới: database transaction bảo vệ điều gì?

Một transaction database có thể nhóm những thay đổi như:

```sql
BEGIN;

INSERT INTO purchase_order (...);
UPDATE inventory SET available = available - 1 WHERE ...;
INSERT INTO payment_record (...);

COMMIT;
```

Nếu transaction rollback, các thay đổi dữ liệu thuộc transaction đó được hủy theo quy tắc DB. Trong JPA, `EntityManager` và persistence context điều phối những thao tác entity, còn transaction manager quyết định commit/rollback.

Nhưng lệnh sau không phải một thao tác SQL của database:

```java
paymentGateway.charge(cardToken, amount);
```

Nó có thể gửi HTTP request tới một hệ thống bên ngoài. Hệ thống đó sở hữu database/transaction của riêng nó và **không tự tham gia vào database transaction JPA của ứng dụng**.

Sơ đồ ranh giới:

```text
                  Ứng dụng Java
                        |
           +------------+------------+
           |                         |
           v                         v
    JPA EntityManager          Payment Gateway API
           |                         |
           v                         v
    Database của ứng dụng       Database của nhà cung cấp
           |                         |
      BEGIN / COMMIT             Transaction riêng
      hoặc ROLLBACK              + kết quả mạng riêng

      Local DB rollback  -X->  Không tự hủy charge bên ngoài
```

Các lời gọi ngoài database thường gặp:

- HTTP/gRPC tới cổng thanh toán, dịch vụ vận chuyển, tra cứu thuế hoặc hệ thống quản lý khách hàng.
- Gửi email, SMS, push notification.
- Publish message tới Kafka, RabbitMQ, SQS hoặc nền tảng tương tự.
- Gửi file lên object storage, chuyển nội dung qua FTP/SFTP.
- Gọi webhook tới đối tác.
- Tương tác với một database khác không tham gia cùng cơ chế transaction đã được phối hợp đúng.
- Thực thi công việc nặng như render PDF, tính báo cáo lớn, ký tài liệu qua dịch vụ ngoài.

Điểm chung không phải “có sử dụng mạng” là luôn sai; vấn đề là **độ trễ, khả năng lỗi và tính nguyên tử không cùng ranh giới với transaction database hiện tại**.

## 2. Vì sao gọi hệ thống ngoài khi giữ transaction là rủi ro?

### 2.1. Transaction kéo dài không kiểm soát

Một câu SQL nội bộ có thể hoàn tất trong vài mili giây, nhưng HTTP request đến hệ thống khác có thể:

- Hoàn tất nhanh nếu mạng tốt.
- Chậm do DNS, TLS handshake, proxy, queue hoặc upstream quá tải.
- Timeout sau vài giây.
- Bị retry theo chính sách client.
- Treo lâu nếu không cấu hình timeout.
- Hoàn tất ở phía đối tác nhưng phản hồi bị mất.

Khi cuộc gọi được đặt **bên trong** một phương thức `@Transactional`, transaction có thể kéo dài đến khi phương thức kết thúc và interceptor transaction thực hiện commit/rollback.

```text
Không nên:

  BEGIN ---- UPDATE inventory ---- HTTP call (4 giây) ---- COMMIT
  |                                                            |
  +---------------- transaction đang mở ----------------------+

Nên hướng tới:

  BEGIN ---- UPDATE inventory / INSERT outbox ---- COMMIT
  |                                                  |
  +---------- transaction ngắn ----------------------+

                                                       HTTP call
                                                       ngoài transaction
```

### 2.2. Lock có thể bị giữ lâu hơn

Nếu transaction trước đó đã cập nhật row tồn kho:

```sql
UPDATE inventory
SET available = available - 1
WHERE product_id = 42;
```

database có thể giữ lock liên quan cho tới commit/rollback. Nếu tiếp theo code chờ payment gateway, những transaction khác muốn cập nhật cùng row có thể phải chờ.

Hậu quả:

- Tăng thời gian chờ lock.
- Tăng nguy cơ deadlock hoặc lock timeout.
- Giảm throughput trên các row “nóng” như tồn kho sự kiện bán hàng.
- Tăng latency của request không hề gọi payment gateway.
- Có thể tạo vòng khuếch đại khi nhiều transaction bị chặn chờ nhau.

Loại lock, thời gian nắm lock và chi tiết isolation phụ thuộc database và lệnh SQL, nên không khẳng định **mọi transaction đọc đều khóa mọi row**. Nhưng giữ transaction mở lâu sau DML làm tăng rủi ro tranh chấp.

### 2.3. Connection pool bị áp lực

Một transaction đang hoạt động thường liên quan đến tài nguyên transaction và có thể giữ JDBC connection trong một phần lớn thời gian của nó. Cơ chế acquisition/release phụ thuộc provider và transaction manager; không nên kết luận transaction luôn giữ đúng một connection từ đầu tới cuối. Dù vậy, long-running transaction có thể gia tăng thời gian tài nguyên bị chiếm dụng.

Ví dụ minh họa:

```text
Connection pool tối đa: 20
Mỗi request:
  SQL thao tác DB: 30 ms
  HTTP đối tác:    3.000 ms

Nếu giữ connection gần cả thời gian:
  ~3.030 ms / request

Nếu transaction DB được rút ngắn:
  ~30 ms DB / request
  HTTP chạy ở bước ngoài transaction
```

Con số này chỉ là ví dụ để hiểu mức độ ảnh hưởng, không phải benchmark. Kết quả thực tế cần đo theo pool, isolation và connection handling của dự án.

### 2.4. Snapshot, undo/redo và tài nguyên DB kéo dài

Ngay cả khi không giữ row lock như một lệnh update, transaction dài có thể:

- Giữ transaction snapshot theo isolation.
- Tăng áp lực phiên bản row/MVCC hoặc cleanup.
- Kéo dài thời gian giữ tài nguyên và log transaction.
- Làm tăng khoảng thời gian có thể bị conflict khi commit.
- Khiến monitoring báo “long-running transaction”.

Tác động cụ thể phụ thuộc PostgreSQL, MySQL/InnoDB, Oracle, SQL Server hoặc DB khác. Không nên dùng một mô tả về row locking của hệ quản trị này làm quy luật cho mọi DB.

### 2.5. Hệ thống ngoài không rollback theo database

```java
@Transactional
public void registerUser(RegisterRequest request) {
    User user = userRepository.save(new User(request.email()));

    emailClient.sendWelcomeMessage(request.email());

    // Bước này có thể thất bại vì UNIQUE/FK/optimistic lock.
    auditRepository.save(new AuditRecord(...));
}
```

Nếu email đã gửi nhưng transaction rollback, người dùng nhận thông báo chào mừng dù user không được tạo thành công. Ngược lại, nếu gửi email thất bại, transaction DB có nên rollback không? Câu trả lời không được quyết định chỉ bởi một exception HTTP; đó là một quyết định nghiệp vụ cần thiết kế.

## 3. Ví dụ phản diện: checkout gọi payment gateway trong @Transactional

Giả sử một ứng dụng bán hàng cần:

1. Kiểm tra giỏ hàng.
2. Tạo đơn hàng.
3. Giảm tồn kho hoặc giữ hàng.
4. Yêu cầu thanh toán.
5. Gửi xác nhận.

Code có vẻ ngắn gọn:

```java
@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;
    private final PaymentGatewayClient paymentGateway;

    public CheckoutService(
            OrderRepository orders,
            InventoryRepository inventory,
            PaymentGatewayClient paymentGateway
    ) {
        this.orders = orders;
        this.inventory = inventory;
        this.paymentGateway = paymentGateway;
    }

    @Transactional
    public Long checkout(CheckoutRequest request) {
        Order order = Order.pending(request.customerId());
        orders.save(order);

        inventory.reserve(order.getItems());

        // Anti-pattern: gọi HTTP khi DB transaction còn mở.
        PaymentResult result = paymentGateway.charge(
            request.paymentMethodToken(),
            order.getTotalAmount()
        );

        order.applyPaymentResult(result);
        return order.getId();
    }
}
```

Ở đây `@Transactional` là annotation `org.springframework.transaction.annotation.Transactional`. Các repository là ví dụ Spring Data JPA và `PaymentGatewayClient` là abstraction cho HTTP/gRPC; đây không phải những API nằm trong JPA chuẩn.

### 3.1. Những kịch bản lỗi

| Kịch bản | DB trong transaction | Payment gateway | Rủi ro |
|---|---|---|---|
| Gateway phản hồi sau 5 giây | Transaction chờ lâu | Có thể thành công | Lock/pool/latency tăng |
| Gateway timeout trước khi xử lý | Transaction có thể rollback | Chưa charge | Có thể retry, nhưng cần xác định trạng thái |
| Gateway charge thành công nhưng response mất | Ứng dụng thấy timeout | Đã trừ tiền | Retry không có idempotency có thể charge hai lần |
| Gateway charge thành công, DB commit thất bại | DB rollback | Đã trừ tiền | Tiền và đơn hàng lệch |
| Gateway trả declined | DB có thể rollback | Không charge | Cần quyết định có giữ record từ chối thanh toán không |
| DB rollback vì optimistic lock | Dữ liệu không được commit | Charge có thể thành công | Không có rollback tự động từ gateway |

**Đặc biệt quan trọng:** Timeout không chứng minh request chưa được phía đối tác thực thi. Nó chỉ chứng minh ứng dụng **chưa nhận được kết quả xác nhận trong thời gian chờ**.

### 3.2. Transaction không biến HTTP thành atomic

Một lời gọi payment bên trong `@Transactional` không phải hai-phase commit. Spring/JPA quản lý database transaction của ứng dụng, còn gateway là participant độc lập.

Ngay cả khi DB transaction manager có JTA, một HTTP API thông thường không tự trở thành tài nguyên XA có thể phối hợp commit. Chỉ khi các thành phần được thiết kế và cấu hình rõ ràng cho distributed transaction tương thích mới có cơ chế phối hợp khác; điều này không phải mặc định và cũng có chi phí riêng.

## 4. Tách ranh giới: transaction ngắn, thao tác ngoài transaction

Hướng đơn giản nhất là tách:

1. Transaction A: ghi trạng thái ban đầu vào DB rồi commit.
2. Gọi hệ thống ngoài **không giữ transaction A**.
3. Transaction B: ghi kết quả nhận được vào DB rồi commit.

```text
HTTP request
    |
    v
[Transaction A]
  - Tạo order PENDING
  - Giữ hàng / ghi trạng thái phù hợp
  - Commit
    |
    v
[Outside transaction]
  - Gọi payment gateway
  - Nhận success / failure / timeout
    |
    v
[Transaction B]
  - Cập nhật order PAYMENT_SUCCEEDED
    hoặc PAYMENT_FAILED / PAYMENT_UNKNOWN
  - Commit
```

Đây là nền tảng của mô hình **state machine** và **saga**. Nhưng tách transaction **không tự tạo tính nguyên tử giữa A, HTTP call và B**: cần trạng thái bền vững, cơ chế retry/compensation và idempotency.

### 4.1. Trạng thái nghiệp vụ tường minh

Ví dụ:

```java
public enum OrderStatus {
    PENDING_PAYMENT,
    PAYMENT_PROCESSING,
    PAID,
    PAYMENT_FAILED,
    PAYMENT_UNKNOWN,
    CANCELLED
}
```

Không nên chỉ có boolean `paid`, vì timeout tạo ra trạng thái **chưa biết kết quả**. Hệ thống cần phân biệt:

- Payment bị từ chối rõ ràng.
- Payment thành công rõ ràng.
- Không có phản hồi, cần đối soát.
- Order bị hủy theo nghiệp vụ.
- Một callback hoặc polling từ gateway đến muộn.

### 4.2. Ba lớp service: ví dụ Spring

```java
@Service
public class CheckoutOrchestrator {

    private final OrderCommandService orderCommands;
    private final PaymentGatewayClient paymentGateway;

    public CheckoutOrchestrator(
            OrderCommandService orderCommands,
            PaymentGatewayClient paymentGateway
    ) {
        this.orderCommands = orderCommands;
        this.paymentGateway = paymentGateway;
    }

    // Không mở transaction DB bao quanh toàn bộ phương thức.
    public Long checkout(CheckoutRequest request) {
        Long orderId =
            orderCommands.createPendingOrder(request);

        try {
            PaymentResult result = paymentGateway.charge(
                request.paymentToken(),
                request.idempotencyKey()
            );

            orderCommands.applyPaymentResult(orderId, result);
        } catch (PaymentTimeoutException ex) {
            orderCommands.markPaymentUnknown(orderId);
        }

        return orderId;
    }
}
```

Và service chỉ thao tác DB:

```java
@Service
public class OrderCommandService {

    private final OrderRepository orders;

    public OrderCommandService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createPendingOrder(CheckoutRequest request) {
        Order order = Order.pendingPayment(
            request.customerId(),
            request.items()
        );
        orders.save(order);
        return order.getId();
    }

    @Transactional
    public void applyPaymentResult(
            Long orderId,
            PaymentResult result
    ) {
        Order order = orders.findById(orderId)
            .orElseThrow();

        order.applyPaymentResult(result);
    }

    @Transactional
    public void markPaymentUnknown(Long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow();

        order.markPaymentUnknown();
    }
}
```

Các class `Order`, `CheckoutRequest`, `PaymentResult` và `PaymentGatewayClient` là abstraction minh họa, chưa phải một chương trình checkout đầy đủ. Code production còn cần idempotency, xác thực callback, trạng thái chuyển hợp lệ, reservation expiration và đối soát.

### 4.3. Vì sao tách thành hai Spring beans?

Trong mô hình Spring proxy-based transaction thông dụng, gọi một method `@Transactional` khác **trong cùng bean** có thể không đi qua transaction interceptor (*self-invocation*). Tách orchestrator và transactional service giúp ranh giới transaction được áp dụng rõ ràng hơn.

Đừng chỉ chuyển HTTP call sang một private method rồi nghĩ transaction đã kết thúc:

```java
@Transactional
public void checkout() {
    saveOrder();
    callExternalPayment(); // Vẫn bên trong transaction!
}
```

Transaction gắn với ranh giới thực thi và interceptor, không phụ thuộc tên method `callExternalPayment`.

### 4.4. Một hệ quả mới: lỗi giữa các bước

Nếu transaction A commit, nhưng tiến trình chết **trước khi gọi gateway**, order có thể mãi PENDING. Nếu gateway charge xong, tiến trình chết **trước transaction B**, order chưa phản ánh kết quả.

Do đó mẫu ba bước chỉ là khung cơ bản. Với yêu cầu tin cậy cao, phải có một **nguồn công việc bền vững** để hệ thống tiếp tục được sau crash — ví dụ transactional outbox.

## 5. Những trường hợp có thể gọi hệ thống ngoài trước transaction

Không phải mọi HTTP call đều cần chạy sau DB transaction. Nếu bước ngoài chỉ dùng để lấy **dữ liệu tham khảo** trước khi ra quyết định, có thể gọi nó trước khi mở transaction:

```java
public QuoteResponse quoteAndCreate(
        QuoteRequest request
) {
    ExternalTaxQuote taxQuote =
        taxClient.calculateTaxes(request.items());

    return commandService.createWithQuote(
        request,
        taxQuote
    );
}
```

`commandService.createWithQuote` mới mở transaction DB để ghi dữ liệu.

Ưu điểm:

- Không giữ DB transaction khi chờ response tax API.
- Không đặt network latency dưới lock transaction.
- Có thể dùng timeout, circuit breaker và cache riêng.

Nhưng cần hiểu giới hạn:

- Dữ liệu quote có thể thay đổi giữa lúc gọi API và lúc commit.
- Tax quote có thời hạn hoặc phiên bản cần lưu lại theo quy tắc nghiệp vụ.
- Nếu gọi ngoài có **side effect** (ví dụ trừ tiền), thực hiện trước DB transaction không còn đơn thuần là tra cứu, và DB commit thất bại có thể tạo trạng thái lệch.
- Kiểm tra một invariant DB trước transaction có thể bị thay đổi bởi transaction khác; cần kiểm tra lại/khóa đúng trong transaction.

**Gợi ý thiết kế:** Phân biệt các lời gọi ngoài **read-only, không thay đổi trạng thái** với các lời gọi **có side effect khó đảo ngược**. Chúng cần chiến lược khác nhau.

## 6. Không gửi thông báo trước commit

Một ví dụ:

```java
@Transactional
public void register(String email) {
    User user = new User(email);
    entityManager.persist(user);

    emailClient.sendWelcome(email); // Không nên.
}
```

Email được gửi trước khi transaction commit có thể khiến user nhận thông báo dù database rollback.

Một cải thiện có giới hạn là **sau commit**:

```java
@Transactional
public void register(String email) {
    User user = new User(email);
    entityManager.persist(user);

    applicationEventPublisher.publishEvent(
        new UserCreatedEvent(user.getId(), email)
    );
}
```

Listener trong Spring:

```java
@Component
public class WelcomeEmailListener {

    private final EmailClient emailClient;

    public WelcomeEmailListener(EmailClient emailClient) {
        this.emailClient = emailClient;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onUserCreated(UserCreatedEvent event) {
        emailClient.sendWelcome(event.email());
    }
}
```

Đoạn này minh họa `@TransactionalEventListener` của Spring, không phải API JPA chuẩn. Sau khi transaction commit, listener có thể bắt đầu công việc gửi email; transaction DB gốc không còn chờ email trong quá trình commit như khi đặt call trong body trước commit.

### 6.1. AFTER_COMMIT giải quyết được gì?

- Không gửi email khi transaction gốc rollback.
- Tách side effect khỏi phần DML trước commit.
- Ranh giới “đã commit” rõ hơn so với `@PostPersist`.

### 6.2. AFTER_COMMIT chưa phải reliable messaging

Vẫn còn rủi ro:

- Tiến trình có thể crash **sau commit nhưng trước khi callback chạy**.
- Email server có thể thất bại khi nhận request.
- Listener đồng bộ có thể giữ thread request lâu sau commit dù DB transaction đã kết thúc.
- Nếu listener làm DB write, có thể cần **transaction mới**; không giả định các write đó tự commit an toàn trong tài nguyên giao dịch đã hoàn tất.
- Nếu dùng `@Async`, job nằm trong memory queue của process cũng có thể mất khi process chết.

Do đó `AFTER_COMMIT` là lựa chọn phù hợp hơn cho tác vụ **best-effort hoặc có hệ thống retry riêng**. Với notification, audit hoặc event cần **không thất lạc sau DB commit**, nên dùng transactional outbox.

### 6.3. JPA @PostPersist không phải AFTER_COMMIT

```java
@PostPersist
void afterPersist() {
    // Chỉ là lifecycle callback, không bảo đảm commit.
}
```

`@PostPersist` có thể chạy trước commit, tùy ID generation và thời điểm INSERT/flush. Không dùng callback này làm bằng chứng dữ liệu đã được commit, cũng không phát ra external side effect không thể rollback từ đây.

## 7. Transactional outbox: ghi ý định gửi cùng transaction DB

Đây là một trong những mẫu quan trọng nhất khi cần:

- Commit dữ liệu nghiệp vụ.
- Sau commit, phát event hoặc gọi hệ thống khác.
- Không đánh mất “ý định phát event” nếu process crash giữa hai bước.
- Cho phép retry khi broker/HTTP gateway tạm thời lỗi.

**Ý tưởng:** Trong **cùng database transaction**, ghi cả **dữ liệu nghiệp vụ** và một **outbox row** thể hiện công việc cần gửi. Một process khác (relay/worker) đọc outbox đã commit rồi thực hiện thao tác ngoài transaction đó.

```text
            HTTP request
                 |
                 v
       +-----------------------+
       | DB transaction ngắn  |
       |-----------------------|
       | INSERT order         |
       | INSERT outbox_event  |
       | COMMIT               |
       +-----------------------+
                 |
                 v
       Database chứa:
         Order PENDING
         Outbox event PENDING
                 |
                 | Sau commit
                 v
       Outbox relay / worker
                 |
                 | đọc event đã commit
                 | kết thúc DB tx
                 v
       Publish message / gọi HTTP
                 |
                 | ack / response
                 v
       DB tx mới: mark PUBLISHED
                 |
                 v
       Consumer hoặc service đích
       xử lý idempotent
```

Ở đây **không có** đoạn code vừa giữ transaction cập nhật order vừa đợi broker trả ACK trong cùng transaction nghiệp vụ.

### 7.1. Schema outbox minh họa

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(40) NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE outbox_event (
    event_id VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    available_at TIMESTAMP NOT NULL,
    claimed_until TIMESTAMP NULL,
    last_error VARCHAR(1000) NULL
);

CREATE INDEX ix_outbox_ready
ON outbox_event(status, available_at, created_at);
```

DDL mang tính định hướng; `TEXT`, timestamp, index và `SKIP LOCKED` tùy hệ quản trị. `event_id` giúp nhận diện một event duy nhất và dùng làm **idempotency/deduplication key**.

Outbox lưu **payload đủ để relay thực hiện công việc**, không nên chỉ lưu reference tới một managed JPA entity hoặc proxy rồi mong worker ở process khác đọc lại object graph trong context cũ.

### 7.2. JPA entity OutboxEvent

```java
package com.example.outbox;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "outbox_event")
public class OutboxEvent {

    @Id
    @Column(name = "event_id", length = 36)
    private String eventId;

    @Column(name = "aggregate_type", nullable = false)
    private String aggregateType;

    @Column(name = "aggregate_id", nullable = false)
    private String aggregateId;

    @Column(name = "event_type", nullable = false)
    private String eventType;

    @Lob
    @Column(name = "payload_json", nullable = false)
    private String payloadJson;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "attempts", nullable = false)
    private int attempts;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "available_at", nullable = false)
    private Instant availableAt;

    @Column(name = "claimed_until")
    private Instant claimedUntil;

    @Column(name = "last_error", length = 1000)
    private String lastError;

    protected OutboxEvent() {
    }

    public static OutboxEvent pending(
            String aggregateType,
            String aggregateId,
            String eventType,
            String payloadJson
    ) {
        OutboxEvent event = new OutboxEvent();
        event.eventId = UUID.randomUUID().toString();
        event.aggregateType = aggregateType;
        event.aggregateId = aggregateId;
        event.eventType = eventType;
        event.payloadJson = payloadJson;
        event.status = "PENDING";
        event.attempts = 0;
        event.createdAt = Instant.now();
        event.availableAt = event.createdAt;
        return event;
    }
}
```

Đây là ví dụ tập trung vào thao tác tạo event. Phần relay cần thêm các phương thức cập nhật claim, retry, status và optimistic/concurrency checks; không nên cho relay thay đổi field trực tiếp mà không có chính sách chuyển trạng thái.

### 7.3. Ghi order và outbox trong cùng transaction

```java
@Service
public class OrderCreationService {

    @PersistenceContext
    private EntityManager em;

    private final ObjectMapper objectMapper;

    public OrderCreationService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command)
            throws JsonProcessingException {

        Order order = Order.pendingPayment(
            command.customerId(),
            command.items()
        );

        em.persist(order);

        // Với IDENTITY hoặc ID strategy cụ thể, có thể
        // cần đồng bộ/chuẩn bị ID theo yêu cầu mapping.
        em.flush();

        PaymentRequestedPayload payload =
            new PaymentRequestedPayload(
                order.getId(),
                order.getTotalAmount(),
                command.paymentMethodTokenReference()
            );

        String payloadJson =
            objectMapper.writeValueAsString(payload);

        OutboxEvent outbox = OutboxEvent.pending(
            "Order",
            order.getId().toString(),
            "PaymentRequested",
            payloadJson
        );

        em.persist(outbox);

        return order.getId();
    }
}
```

`ObjectMapper`/`JsonProcessingException` thuộc Jackson, `@Service`/`@Transactional` thuộc Spring và các class `Order`/`PaymentRequestedPayload` là domain types minh họa. Nếu method khai báo checked exception, cần cấu hình **rollback policy** thích hợp trong Spring (ví dụ `rollbackFor`), hoặc chuyển payload serialization sang một bước xác thực trước khi mở transaction. Ví dụ trên giả định serialization hợp lệ; code production không nên để checked exception ngoài chính sách rollback mong muốn.

Trong transaction:

- Nếu ghi order thất bại, outbox không commit.
- Nếu ghi outbox thất bại, order cũng không commit.
- Nếu cả hai thành công, order và event cùng được commit.
- Payment gateway **chưa được gọi** ở transaction này.

Không nên chèn lời gọi broker hoặc gateway giữa `em.persist(order)` và `em.persist(outbox)`.

### 7.4. Nguồn sự thật sau commit

Sau commit, outbox row là **bằng chứng bền vững** rằng hệ thống cần tiếp tục gửi event.

Nếu tiến trình API crash ngay sau commit:

- Row order vẫn tồn tại.
- Row outbox vẫn tồn tại.
- Relay chạy độc lập có thể tiếp tục gửi event.

Nếu transaction rollback:

- Cả order lẫn outbox event đều không được commit.
- Relay sẽ không thấy event đã rollback.

Đây là lợi ích trọng tâm: **atomic DB write của business record và “ý định gửi”**. Nó không biến external message publication thành chính phần commit DB.

## 8. Relay: lấy công việc DB rồi gọi bên ngoài khi không giữ transaction

Một relay đúng cần tách ít nhất ba bước:

1. **Claim** công việc trong DB transaction ngắn.
2. **Publish/call HTTP** ở ngoài DB transaction.
3. **Mark success/failure** trong một DB transaction mới.

```text
Transaction A: claim event
    BEGIN
    SELECT/UPDATE một nhóm event PENDING
    status=CLAIMED, lease_until=...
    COMMIT

Không có DB transaction đang mở:
    broker.publish(event) hoặc httpClient.call(event)

Transaction B: cập nhật kết quả
    BEGIN
    status=PUBLISHED hoặc retry schedule
    COMMIT
```

Một worker không nên:

```java
@Transactional
public void publishPending() {
    List<OutboxEvent> events = selectPendingAndLockRows();

    for (OutboxEvent event : events) {
        broker.publish(event); // Anti-pattern: gửi khi giữ DB lock!
        event.markPublished();
    }
}
```

Đoạn trên di chuyển vấn đề từ web request sang background job, nhưng vẫn giữ transaction mở khi chờ broker và làm tăng lock contention.

### 8.1. Phác thảo thuật toán relay

```java
public void runBatch() {
    List<OutboxMessage> batch =
        outboxCommands.claimReadyBatch(50);
        // claimReadyBatch chạy và commit một DB transaction ngắn.

    for (OutboxMessage message : batch) {
        try {
            broker.publishAndWaitForAck(
                message.eventId(),
                message.eventType(),
                message.payloadJson()
            );

            outboxCommands.markPublished(
                message.eventId(),
                message.claimToken()
            );
            // Transaction mới, không đợi mạng bên trong.
        } catch (TransientBrokerException ex) {
            outboxCommands.scheduleRetry(
                message.eventId(),
                message.claimToken(),
                ex.getMessage()
            );
        }
    }
}
```

`OutboxMessage` là DTO chứa payload đã đọc từ DB. `claimToken` nhận diện lượt claim để một worker bị hết lease không thể ghi đè kết quả của worker khác; `outboxCommands` phải có transactional methods do framework thực sự áp dụng.

Tương tự như mọi code minh họa, `broker.publishAndWaitForAck` cần timeout hữu hạn. Nếu publish bị treo, nó vẫn ảnh hưởng worker thread, nhưng **không nên giữ DB transaction/lock trong lúc chờ**.

### 8.2. Claim an toàn khi nhiều worker

Nếu hai worker cùng đọc các row `PENDING` mà không lock/claim atomic, cả hai có thể phát cùng event.

Một phương án database-specific là lock các row sẵn sàng và dùng `SKIP LOCKED`, rồi cập nhật lease trong transaction ngắn. Ví dụ dạng khái niệm cho PostgreSQL:

```sql
BEGIN;

SELECT event_id
FROM outbox_event
WHERE
    (status = 'PENDING' AND available_at <= CURRENT_TIMESTAMP)
    OR (status = 'CLAIMED' AND claimed_until < CURRENT_TIMESTAMP)
ORDER BY created_at, event_id
FOR UPDATE SKIP LOCKED
LIMIT 50;

-- Với các event vừa claim, UPDATE status='CLAIMED',
-- claimed_until=..., attempts=attempts+1, claim_token=...
-- trong cùng transaction trước COMMIT.

COMMIT;
```

Lưu ý:

- `FOR UPDATE SKIP LOCKED` không phải SQL portable cho mọi database.
- DDL mẫu cần bổ sung `claim_token` nếu dùng fencing token như trong pseudocode.
- Lease cần hết hạn để worker khác có thể xử lý event bị bỏ dở.
- Chuyển trạng thái phải atomic, tránh worker chậm đánh dấu thành công sau khi claim đã thuộc worker khác.
- Relay cần backoff, giới hạn retry, dead-letter/quarantine và cảnh báo vận hành.
- Nếu event cần thứ tự theo aggregate, polling nhiều worker có thể làm mất ordering; cần cơ chế sequence/partition theo aggregate.

Vì yêu cầu từng hệ thống khác nhau, có thể dùng CDC (change-data capture) để chuyển outbox row sang broker thay vì polling. Dù cách nào, nguyên tắc vẫn là **ghi event cùng transaction với business data**, còn network publication nằm ngoài transaction đó.

## 9. Outbox không bảo đảm exactly-once delivery

Một tình huống quan trọng:

```text
T1: Relay claim event E.
T2: Relay publish E lên broker thành công.
T3: Broker trả ACK.
T4: Process relay crash trước khi mark E=PUBLISHED.
T5: Lease hết hạn, worker khác claim E và publish lại.
```

Broker có thể nhận **hai bản sao của cùng event E**. Outbox giải quyết việc **không đánh mất ý định gửi**, nhưng không tự bảo đảm không bao giờ gửi trùng.

Do đó, thiết kế thường nhắm tới:

- **At-least-once delivery** cho công việc có retry.
- **Idempotent consumer** hoặc thao tác idempotent ở service đích.
- **Event ID ổn định**, không tạo ID mới mỗi lần retry.
- **Deduplication** và state machine để side effect chỉ được áp dụng một lần theo nghiệp vụ.
- Quan sát và đối soát để phát hiện event quá hạn hoặc không thể xử lý.

### 9.1. Deduplicate consumer cập nhật database

Một consumer nhận event từ broker có thể dùng bảng:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong transaction của consumer:

```text
BEGIN
  INSERT processed_message(consumer_name, event_id, ...)
  Nếu PK conflict -> event đã xử lý -> bỏ qua
  Nếu insert thành công -> cập nhật business DB
COMMIT
ACK broker sau khi commit
```

Cần để **ghi dedup marker và cập nhật business data trong cùng DB transaction**. Nếu marker commit nhưng business update không commit, hoặc ngược lại, consumer vẫn có thể sai. Với consumer chỉ gọi một external HTTP API, dedup DB đơn thuần chưa tạo atomicity với HTTP, nên cần idempotency key/đối soát tại hệ thống đích.

### 9.2. Idempotency key cho payment gateway

Giả sử mỗi đơn được phép tạo một payment attempt cụ thể với ID ổn định:

```java
String idempotencyKey = paymentAttempt.getId().toString();

paymentGateway.charge(
    paymentAttempt.getAmount(),
    paymentAttempt.getPaymentMethodReference(),
    idempotencyKey
);
```

Nếu client timeout hoặc relay retry, vẫn dùng **cùng key** cho cùng attempt, theo contract của nhà cung cấp gateway. Không phát sinh random key mới trong mỗi lần retry, vì gateway có thể coi đó là yêu cầu thanh toán độc lập và trừ tiền lần nữa.

Cần kiểm tra tài liệu của gateway: phạm vi key, thời gian lưu key, tham số nào phải trùng, cách query status và ý nghĩa response timeout. Không giả định mọi nhà cung cấp đều thực hiện idempotency giống nhau.

### 9.3. Callback webhook có thể đến trùng hoặc sai thứ tự

Gateway thường gửi webhook nhiều lần để bảo đảm delivery. Xử lý nên:

1. Xác minh chữ ký và nguồn gửi theo cơ chế của provider.
2. Nhận diện event/payment ID ổn định.
3. Deduplicate theo event ID.
4. Đọc trạng thái business hiện tại trong transaction.
5. Chỉ thực hiện những state transition hợp lệ.
6. Cập nhật payment/order atomically trong DB.
7. ACK webhook theo hợp đồng sau xử lý thích hợp.
8. Có đường đối soát khi callback bị trễ/mất.

Một callback “payment succeeded” không nên chuyển đơn từ `REFUNDED` hoặc `CANCELLED` sang `PAID` chỉ vì nó tới muộn. State machine là lớp bảo vệ cần thiết.

## 10. Saga và trạng thái chờ cho quy trình nhiều hệ thống

Khi một nghiệp vụ liên quan nhiều hệ thống có transaction riêng, việc cố bao tất cả trong một `@Transactional` là không phù hợp. **Saga** chia quy trình thành nhiều bước có kết quả bền vững, mỗi bước có transaction cục bộ và có thể cần **compensating action** khi một bước sau thất bại.

Ví dụ đặt hàng:

```text
              Create order
                   |
                   v
            Order=PENDING
                   |
                   v
           Reserve inventory
                /      \
             FAIL       OK
              |          |
              v          v
         Order=FAILED   Authorize payment
                          /        \
                       FAIL        OK
                        |           |
                        v           v
                 Release inventory  Confirm order
                        |           |
                        v           v
                   Order=FAILED    Order=PAID
```

Giữa các bước, không cần giữ một database transaction dài. Mỗi bước ghi trạng thái cục bộ rồi commit; công việc tiếp theo được điều phối bằng event/outbox, job hoặc orchestrator có state bền vững.

### 10.1. Compensation không phải rollback tuyệt đối

Nếu đã gửi hàng, việc “hủy bước gửi hàng” có thể không thực hiện được hoàn toàn; compensation có thể phải tạo quy trình hoàn trả thay vì đảo ngược chính xác dữ liệu. Nếu gateway đã charge, compensation có thể là refund, nhưng refund có latency/phí/trạng thái thất bại riêng.

Vì vậy saga không hứa tính nguyên tử ACID xuyên mọi hệ thống. Nó giúp đưa nghiệp vụ về **trạng thái cuối cùng hợp lệ và có thể phục hồi**, thông qua state transition, retry và compensation được định nghĩa rõ.

### 10.2. Thiết kế reservation với thời hạn

Nếu cần giữ một sản phẩm trong lúc chờ thanh toán:

- Transaction ngắn tạo `InventoryReservation` và giảm available stock hoặc dùng constraint phù hợp.
- Reservation có `expiresAt` và trạng thái `RESERVED`.
- Payment được gọi ngoài transaction.
- Khi paid, transaction mới chuyển reservation thành `CONFIRMED`.
- Khi failed/timeout quá hạn, job giải phóng reservation bằng thao tác idempotent.

Đây là cách tránh giữ **row lock lâu bằng transaction mở** trong lúc người dùng hoặc gateway xử lý thanh toán.

### 10.3. Không giữ transaction mở để chờ người dùng

Các thao tác như người dùng nhập OTP, xác thực 3-D Secure, chọn shipping option hoặc chờ phê duyệt thủ công có thể mất vài phút hoặc giờ. Không giữ JPA transaction/EntityManager liên tục suốt một “business conversation” dài như vậy. Lưu trạng thái trung gian và mở transaction mới cho mỗi bước.

## 11. Phân biệt timeout, failure và unknown outcome

Một HTTP client timeout có ít nhất hai tình huống:

- Request chưa tới server hoặc chưa được xử lý.
- Request đã được server xử lý nhưng response không đến client.

Vì vậy một exception timeout nên thường được ánh xạ thành **UNKNOWN** thay vì mặc định FAILED cho operation có side effect.

```text
                    paymentGateway.charge(...)
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
           Success          Declined          Timeout
              |               |               |
              v               v               v
            PAID        PAYMENT_FAILED     PAYMENT_UNKNOWN
                                                |
                                                v
                                          Query provider
                                          / webhook / retry
                                          với cùng idempotency key
```

Phải tránh vòng:

```java
for (int attempt = 0; attempt < 5; attempt++) {
    paymentGateway.charge(amount, randomUUID());
}
```

Nếu mỗi retry có ID mới, nhiều charge có thể được thực hiện. Thay bằng **một payment attempt ID ổn định**, kiểm tra chính sách retry của gateway và đối soát khi kết quả không rõ.

### 11.1. Timeout có giới hạn là bắt buộc

Ngay cả khi HTTP chạy ngoài DB transaction, request hoặc worker vẫn có thể bị treo nếu client không cấu hình timeout.

Cần giới hạn phù hợp:

- Connection timeout.
- Request/response/read timeout.
- Overall deadline.
- Retry count và exponential backoff/jitter.
- Circuit breaker để tránh kéo hệ thống xuống khi upstream quá tải.
- Bulkhead/concurrency limit cho mỗi downstream.
- Idempotency khi retry.

Các kỹ thuật này **không thay thế** việc tách DB transaction, mà bổ sung cho khả năng phục hồi của kiến trúc.

## 12. Gọi service ngoài để xác thực: dùng cache hoặc snapshot khi phù hợp

Một số use case cần đọc dữ liệu của service khác, ví dụ quyền mua hàng, điểm tín dụng, giá vận chuyển hoặc mức thuế.

Có thể cân nhắc:

- Gọi API ngoài **trước** DB transaction nếu request chỉ đọc và có thể chấp nhận độ trễ dữ liệu.
- Dùng snapshot/version của dữ liệu tham khảo để ghi lại điều kiện đã áp dụng.
- Đồng bộ reference data vào database nội bộ theo event để tránh phụ thuộc mạng trên hot path.
- Nếu invariant bắt buộc nhất quán tức thời giữa hai service, thiết kế lại ownership dữ liệu hoặc protocol thay vì chỉ tăng transaction timeout.

Đừng làm:

```java
@Transactional
public void approve(Order order) {
    lockOrderRow(order.id());

    CreditScore score = creditApi.fetch(order.customerId());
    // Giữ lock order trong khi gọi API ngoài.
    ...
}
```

Nếu điểm tín dụng là đầu vào tính toán, gọi nó trước khi lock hàng DB có thể giảm thời gian transaction. Nhưng nếu điều kiện dựa trên DB có thể bị thay đổi, cần xác thực hoặc áp dụng concurrency control **sau khi mở transaction**.

## 13. JPA flush không làm hệ thống ngoài trở thành transactional

Một ngộ nhận thường gặp:

```java
@Transactional
public void process() {
    entityManager.persist(order);
    entityManager.flush();

    externalClient.send(order);
}
```

Người viết code nghĩ: “Đã flush thì DB đã ghi, gửi external sẽ an toàn”.

Điều đó sai vì:

- `flush()` gửi SQL trong transaction, nhưng chưa commit.
- Database vẫn có thể rollback.
- External side effect không tự bị hủy khi rollback.
- Flush có thể đồng bộ **nhiều pending entity**, không riêng order.
- Query hoặc IDENTITY có thể khiến SQL chạy trước flush, nhưng vẫn chưa commit.
- Lỗi có thể xuất hiện ở commit do deferred constraint, transaction conflict hoặc sự cố khác.

Nếu external message phải chỉ tồn tại khi order commit, dùng **outbox** hoặc cơ chế after-commit phù hợp với yêu cầu reliability, không xem flush là “mini commit”.

## 14. Transaction propagation không phải cách che giấu lời gọi ngoài

Một số người cố khắc phục bằng cách thêm:

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void callExternal() {
    externalClient.call();
}
```

Khi được gọi qua Spring proxy đúng cách, `NOT_SUPPORTED` có thể suspend transaction hiện tại trong phạm vi method. Nhưng điều này **không tự giải quyết nguyên tử hóa**:

- Transaction gốc có thể vẫn giữ state/lock và tài nguyên liên quan khi bị suspend.
- Sau external call, transaction gốc có thể resume rồi rollback.
- External side effect đã xảy ra không được rollback cùng.
- Self-invocation có thể làm propagation không được áp dụng.
- Việc thiết kế unit-of-work vẫn chưa rõ ràng.

Tương tự, `REQUIRES_NEW` tạo một transaction độc lập cho database work, nhưng **không nên dùng để gọi HTTP bên trong một transaction DB mới**. Nó có thể làm tăng số connection cần mượn và tạo những commit độc lập khó phối hợp.

**Cách tốt hơn:** tổ chức ranh giới service/workflow rõ ràng để phần external I/O chạy **sau khi transaction DB ngắn đã hoàn tất**, hoặc dùng outbox/worker.

## 15. EntityManager và lazy loading sau khi tách transaction

Tách HTTP ra ngoài transaction có một hệ quả: các entity JPA đã được trả ra ngoài service có thể trở thành **detached** hoặc association còn `LAZY` không tải được.

Ví dụ:

```java
Order order = orderCommandService.createPendingOrder(...);

// Sau transaction, có thể không đọc lazy association an toàn:
String customerEmail = order.getCustomer().getEmail();
```

Không nên giải quyết bằng cách **giữ transaction mở chỉ để HTTP client có thể duyệt entity graph**.

Thay vào đó, tạo **DTO bất biến** chứa dữ liệu cần cho external call trước khi transaction kết thúc:

```java
public record PaymentRequestData(
    Long orderId,
    String paymentAttemptId,
    BigDecimal amount,
    String currency,
    String paymentMethodReference
) { }
```

Transactional service trả DTO hoặc ghi payload vào outbox. Orchestrator/relay sử dụng DTO đó ngoài transaction, không cần giữ `EntityManager` hoặc lazy proxy mở.

### 15.1. Không trả thẳng managed entity qua message broker

Message payload nên có schema/version, ID và các field đã lựa chọn; không serialize toàn bộ entity, vì:

- Lazy loading có thể phát thêm SQL.
- Quan hệ hai chiều có thể lặp vô hạn khi serialize.
- Payload chứa các field nội bộ không cần thiết.
- Entity schema thay đổi làm contract message khó tương thích.
- Context của producer không tồn tại ở consumer.

Outbox nên ghi dữ liệu đủ dùng cho consumer hoặc chỉ các ID có contract truy vấn rõ ràng, tùy độ ổn định và yêu cầu business.

## 16. Xử lý thứ tự event và trạng thái chuyển hợp lệ

Outbox có thể gửi trùng hoặc không theo thứ tự tuyệt đối khi có nhiều workers, partitions và retry.

Giả sử hai event cho cùng đơn:

```text
OrderCreated(orderId=100)
OrderCancelled(orderId=100)
```

Nếu consumer nhận Cancelled trước Created, việc áp dụng ngây thơ có thể khiến order trở lại trạng thái PENDING sau khi đã CANCELLED.

Hướng xử lý:

- Đưa `aggregateId` vào event.
- Nếu cần, có sequence/version theo từng aggregate.
- Dùng partition/ordering key cùng aggregate trên broker hỗ trợ.
- Consumer áp dụng state transition có kiểm tra version/current status.
- Event có stable ID để dedup.
- Cho phép retry/reconciliation khi event đến muộn.
- Không giả định chỉ vì event được INSERT trước thì worker publish trước trong mọi trường hợp.

### 16.1. Ví dụ chuyển trạng thái có điều kiện

```java
@Transactional
public void onPaymentSucceeded(PaymentSucceeded event) {
    Order order = orders.findById(event.orderId())
        .orElseThrow();

    if (order.isPaid()) {
        return; // Xử lý lặp phù hợp.
    }

    if (!order.canTransitionToPaid()) {
        // Ghi nhận conflict/đối soát thay vì ghi đè mù quáng.
        throw new IllegalStateException(
            "Trạng thái đơn hàng không cho phép PAID"
        );
    }

    order.markPaid(event.paymentId());
}
```

Đoạn này cần kết hợp dedup marker và constraint/version trong transaction để chống hai consumer cùng xử lý. `if (order.isPaid())` trong Java một mình không loại bỏ race condition.

## 17. Quan sát trong production: đo cái gì?

Nếu nghi ngờ application giữ transaction quá lâu, cần có dữ liệu đo.

Một dashboard hữu ích gồm:

| Chỉ số | Mục đích |
|---|---|
| Thời gian transaction p50/p95/p99 | Phát hiện giao dịch dài |
| Thời gian giữ JDBC connection | Biết áp lực resource pool |
| Connection pool active/idle/pending | Phát hiện cạn pool |
| DB lock wait/blocked transactions | Xác định contention |
| Thời gian gọi từng downstream p95/p99 | Tìm nguyên nhân I/O chậm |
| HTTP timeout/error rate | Phát hiện downstream bất ổn |
| DB deadlock/lock timeout | Đánh giá ảnh hưởng transaction dài |
| Outbox event backlog | Theo dõi công việc chưa phát |
| Tuổi event PENDING lâu nhất | Phát hiện relay bị kẹt |
| Outbox retry/failed/claimed-expired | Giám sát reliability |
| Consumer dedup hit rate | Theo dõi message trùng |
| Payment UNKNOWN lâu nhất | Phát hiện giao dịch cần đối soát |
| Số order PENDING quá SLA | Phát hiện workflow không hoàn tất |

Một trace nên phân biệt các span:

```text
HTTP POST /checkout
  ├─ DB transaction: create pending order  25 ms
  ├─ External payment call               1.200 ms
  └─ DB transaction: apply result          18 ms
```

Với outbox:

```text
HTTP POST /checkout
  └─ DB transaction: order + outbox       30 ms

Outbox relay
  ├─ DB transaction: claim                10 ms
  ├─ Broker publish                      90 ms
  └─ DB transaction: mark published        8 ms
```

Các con số minh họa. Cần dùng trace/log thực tế và bảo vệ dữ liệu nhạy cảm. **Không ghi thô payment token, thông tin thẻ, mật khẩu hoặc payload chứa bí mật** vào outbox/diagnostic logs.

## 18. Kiểm thử kịch bản lỗi thay vì chỉ happy path

Một thiết kế không gọi hệ thống ngoài khi giữ DB transaction cần được kiểm thử các **điểm crash và failure**.

### 18.1. Lỗi trước commit business transaction

Thiết lập DB constraint khiến `createOrder` hoặc `insertOutbox` thất bại.

**Kỳ vọng:** Không có order commit và không có outbox row commit. Relay không được gửi event đã rollback.

### 18.2. Crash ngay sau commit

Giả lập process dừng ngay sau khi transaction chứa order + outbox đã commit nhưng trước lúc relay chạy.

**Kỳ vọng:** Sau khi worker khởi động lại, nó vẫn tìm được outbox event đã commit và có thể xử lý.

### 18.3. Broker từ chối hoặc timeout

Relay claim một event, rồi broker trả lỗi mạng.

**Kỳ vọng:** Event không bị đánh dấu thành công giả, được retry với backoff/lease và cuối cùng có đường dead-letter/quarantine nếu vượt chính sách.

### 18.4. Broker ACK rồi relay crash trước mark

**Kỳ vọng:** Event có thể được gửi lại; consumer dedup hoặc idempotency key ngăn side effect nghiệp vụ bị áp dụng hai lần.

### 18.5. Callback đến trùng

Gateway gửi PaymentSucceeded cùng event ID hai lần.

**Kỳ vọng:** Order chỉ được chuyển trạng thái theo quy tắc một lần, dedup marker/constraint được ghi atomically.

### 18.6. Callback đến muộn

Order đã timeout và chuyển CANCELLED; PaymentSucceeded đến sau.

**Kỳ vọng:** Không tự ghi đè trạng thái vô điều kiện. Quy trình đối soát/refund/compensation được áp dụng theo state machine.

### 18.7. Đồng thời tranh chấp tồn kho

Hai giao dịch cùng cố giữ đơn vị hàng cuối cùng.

**Kỳ vọng:** DB constraint, conditional update, version hoặc lock bảo vệ invariant ngay cả khi không giữ transaction trong lúc gọi gateway.

### 18.8. Transaction timeout

Giả lập downstream chậm và theo dõi transaction lifespan.

**Kỳ vọng:** External call nằm ngoài business DB transaction. Nếu client vẫn xử lý synchronous, thời gian request có thể dài, nhưng DB transaction không chờ mạng theo cùng cách.

## 19. Một số phương án thiết kế và điểm đánh đổi

| Giải pháp | Có giữ DB transaction trong lúc gọi ngoài? | Ưu điểm | Hạn chế |
|---|---|---|---|
| Gọi HTTP ngay trong `@Transactional` | Có thể có | Code đơn giản | Lock/pool lâu; không atomic với HTTP |
| Gọi read-only external API trước DB transaction | Không | Tách latency mạng khỏi DB | Dữ liệu tham khảo có thể stale; cần revalidate |
| Commit transaction A, gọi HTTP, transaction B cập nhật | Không giữ transaction A | Dễ hiểu, phù hợp workflow nhỏ | Crash giữa bước cần recovery |
| `@TransactionalEventListener(AFTER_COMMIT)` | Không ở phần DB ghi trước commit | Không gửi nếu DB rollback | Callback in-memory có thể mất khi crash |
| Transactional outbox + relay | Không ở business DB transaction | Intent gửi bền vững, retry được | Phức tạp hơn; at-least-once, cần dedup |
| Saga/state machine | Mỗi bước một transaction ngắn | Xử lý nhiều hệ thống, compensation | Eventual consistency, nhiều trạng thái |
| Distributed/XA transaction nếu mọi resource thực sự hỗ trợ | Phụ thuộc giao thức | Có thể phối hợp một số resource | Chi phí/khả năng hỗ trợ/availability; HTTP thường không XA |

**Không có một lựa chọn duy nhất cho mọi use case.** Gửi email thông báo best-effort có thể chấp nhận after-commit; thanh toán và xuất kho đòi hỏi trạng thái bền vững, idempotency và đối soát; báo cáo chỉ đọc có thể cần gọi API ngoài trước transaction mà không cần outbox.

## 20. Những lỗi tư duy và cách sửa

### 20.1. “@Transactional sẽ rollback cả HTTP call”

**Sai.** DB transaction không tự điều phối rollback của dịch vụ HTTP ngoài. Cần protocol phân tán/compensation/idempotency phù hợp.

### 20.2. “Nếu HTTP chậm, chỉ cần tăng transaction timeout”

**Không giải quyết gốc rễ.** Timeout lớn có thể làm giao dịch giữ resource lâu hơn. Tách external I/O và giữ transaction ngắn thường là giải pháp kiến trúc tốt hơn.

### 20.3. “Flush thành công là có thể thanh toán an toàn”

**Sai.** Flush chưa commit; commit vẫn có thể thất bại.

### 20.4. “Gọi hệ thống ngoài trong transaction để bảo đảm nguyên tử”

**Sai với HTTP thông thường.** Transaction DB và external service không tự chia sẻ commit/rollback.

### 20.5. “Chuyển HTTP call sang method @Async là xong”

**Chưa đủ.** Nếu job chỉ nằm trong memory queue, crash có thể làm mất việc; async cũng có thể bắt đầu trước commit nếu scheduling diễn ra trong transaction. Cần after-commit đúng ranh giới hoặc outbox khi cần durability.

### 20.6. “After-commit listener không bao giờ mất event”

**Sai.** Process có thể chết sau commit nhưng trước khi listener chạy. Outbox lưu intent bền vững hơn.

### 20.7. “Outbox bảo đảm exactly-once”

**Sai.** Relay crash sau publish nhưng trước mark có thể gây publish trùng. Consumer/idempotency phải xử lý.

### 20.8. “Có event ID rồi thì khỏi cần DB dedup”

**Sai.** Event ID giúp nhận diện, nhưng consumer phải lưu/kiểm tra nó đúng cách cùng business changes để ngăn xử lý lặp.

### 20.9. “Payment timeout nghĩa là chưa charge”

**Sai.** Outcome có thể UNKNOWN. Cần query gateway/webhook/idempotent retry/đối soát.

### 20.10. “Chỉ cần transaction A commit rồi gọi HTTP là đáng tin”

**Chưa đủ khi yêu cầu không thất lạc.** Crash giữa commit và external call vẫn có thể làm mất công việc. Cần persistent job/outbox hoặc workflow recovery.

### 20.11. “Giữ @Transactional nhưng NOT_SUPPORTED cho một helper giải quyết mọi vấn đề”

**Sai.** Suspend transaction không tự loại bỏ khả năng DB rollback sau external side effect, lock/resource cũng có thể còn bị giữ và self-invocation có thể không áp dụng proxy.

### 20.12. “Mọi DB transaction đều giữ tất cả row lock ngay khi begin”

**Sai.** Locking phụ thuộc SQL, isolation và database. Tuy nhiên transaction dài làm tăng thời gian nắm giữ các tài nguyên/lock đã có.

### 20.13. “Dùng REQUIRES_NEW để gọi HTTP sẽ an toàn”

**Sai.** REQUIRES_NEW điều phối DB transaction mới; HTTP vẫn không trở thành atomic với DB, thậm chí có thể thêm áp lực connection.

### 20.14. “Gửi message ngay sau entityManager.persist là đã chắc chắn row tồn tại”

**Sai.** `persist` có thể chưa INSERT; transaction chưa commit. Message consumer có thể đọc không thấy order hoặc order sau đó rollback.

### 20.15. “Callback @PostPersist là tín hiệu sau commit”

**Sai.** Đây là lifecycle callback, không phải transaction-committed event.

### 20.16. “Không cần transaction khi cập nhật kết quả webhook”

**Sai.** Việc dedup, kiểm tra trạng thái và cập nhật order/payment cần atomic trong DB theo nghiệp vụ.

### 20.17. “Retry HTTP với random key khác không sao”

**Sai với side effect như charge.** Có thể tạo nhiều yêu cầu thanh toán thực. Cần key ổn định cho cùng một logical operation.

### 20.18. “Outbox relay publish khi giữ SELECT FOR UPDATE lock là bình thường”

**Không nên.** Nó tái tạo long-running transaction trong worker. Claim và commit nhanh rồi publish ở ngoài transaction.

### 20.19. “Nếu dùng JPA entity cho payload thì worker có thể dùng luôn lazy association”

**Sai.** Worker/process khác không dùng persistence context cũ. Lưu DTO/schema payload rõ ràng.

### 20.20. “Giảm transaction duration là đủ để ngăn double booking”

**Chưa đủ.** Concurrency invariant vẫn phải được bảo vệ bằng version, constraint, conditional SQL hoặc lock trong transaction ngắn.

### 20.21. “Sau khi commit trả HTTP 200 thì toàn bộ saga đã hoàn thành”

**Không nhất thiết.** Nếu bước payment/fulfillment chạy bất đồng bộ, API nên phản ánh trạng thái hiện tại và cung cấp cách theo dõi tiến trình; 202 Accepted hoặc status endpoint có thể phù hợp hơn tùy contract.

## 21. Quy trình thiết kế an toàn cho một thao tác JPA có external I/O

Có thể đi theo các bước:

1. **Liệt kê tất cả thao tác**: thao tác nào là database DML, thao tác nào gọi hệ thống khác, thao tác nào chỉ tính toán trong bộ nhớ?
2. **Xác định invariants** phải nguyên tử trong một database: ví dụ tạo order và reservation, update balance nội bộ, ghi payment attempt.
3. **Đặt transaction ngắn** xung quanh đúng các DML cần nguyên tử. Tránh delay, sleep, HTTP, email, file upload, chờ người dùng.
4. **Phân loại external call**: chỉ đọc, best-effort notification, hay có side effect tài chính/khó đảo ngược.
5. **Chọn workflow**: external read trước transaction; after-commit cho tác vụ chấp nhận best-effort; outbox/saga cho công việc phải tiếp tục sau crash.
6. **Ghi trạng thái bền vững** cho những bước đang chờ, thất bại hoặc không rõ kết quả.
7. **Định nghĩa retry/idempotency** với event ID, payment attempt ID hoặc operation key ổn định.
8. **Đảm bảo race-condition safety** bằng constraint, optimistic/pessimistic locking hoặc conditional update trong transaction ngắn.
9. **Thiết kế đối soát và compensation** khi external đã thành công nhưng bước DB sau thất bại.
10. **Quan sát metrics**: transaction duration, pool, lock wait, outbox backlog, retries, unknown payments.
11. **Thử các điểm crash** trước/sau commit, sau publish trước mark, callback trùng hoặc tới muộn.
12. **Tài liệu hóa semantic của API**: trả đồng bộ khi nào, trạng thái PENDING/PAID/FAILED/UNKNOWN nghĩa gì và client phải kiểm tra lại bằng cách nào.

Sơ đồ lựa chọn:

```text
             Cần gọi hệ thống ngoài?
                       |
                       v
             Call chỉ đọc, không side effect?
                 /                    \
                Có                    Không
                |                      |
                v                      v
      Có thể gọi trước tx?      Có thể mất công việc
         /       \              sau commit không?
        Có       Không             /         \
         |         |              Có         Không
         v         v               |           |
      Gọi rồi     Tách hoặc         v           v
      validate    snapshot       AFTER_COMMIT   Outbox + relay
      khi mở tx   phù hợp         phù hợp        + idempotency
                                                  |
                                                  v
                                          Nhiều bước/services?
                                             /          \
                                           Không        Có
                                            |            |
                                            v            v
                                          Retry       Saga/state
                                          + dedup     machine +
                                                      compensation
```

Nếu một external side effect không thể đảo ngược, các phương án “gọi trước transaction” và “gọi sau transaction” đều phải tính đến crash/partial failure. Với nghiệp vụ tài chính, sử dụng provider idempotency, payment states, webhook verification và reconciliation là các thành phần thiết kế cốt lõi.

## 22. Bài tập thực hành có gợi ý

### Bài 1: Phát hiện transaction kéo dài

```java
@Transactional
public void createOrder(CheckoutCommand command) {
    orderRepository.save(Order.from(command));
    shippingClient.calculateShipping(command.address());
}
```

**Câu hỏi:** Rủi ro là gì nếu shipping API chậm 5 giây?

**Gợi ý:** DB transaction vẫn mở trong lúc gọi ngoài; có thể giữ connection/lock/snapshot và làm tăng latency/contestion. Nếu chỉ là tính báo giá, cân nhắc gọi shipping API trước transaction rồi validate dữ liệu phù hợp khi ghi DB.

### Bài 2: Flush và email

```java
em.persist(user);
em.flush();
mailClient.sendWelcome(user.getEmail());
```

**Câu hỏi:** Vì sao cách này vẫn có thể gửi mail sai?

**Gợi ý:** Flush không commit. Transaction có thể rollback sau khi mail đã gửi.

### Bài 3: After-commit callback

Một service publish event qua Spring `@TransactionalEventListener(AFTER_COMMIT)`.

**Câu hỏi:** Crash ngay sau commit nhưng trước listener sẽ gây gì?

**Gợi ý:** Sự kiện có thể không được phát; nếu yêu cầu durability, lưu outbox event cùng transaction.

### Bài 4: Outbox atomicity

Transaction tạo Order và ghi OutboxEvent trong cùng database.

**Câu hỏi:** Nếu transaction rollback, relay nên thấy gì?

**Gợi ý:** Không thấy order/outbox đã rollback. Hai row phải commit cùng nhau hoặc cùng không commit.

### Bài 5: Crash sau publish

Relay publish event rồi crash trước khi đánh dấu `PUBLISHED`.

**Câu hỏi:** Điều gì xảy ra khi retry?

**Gợi ý:** Có thể publish trùng. Consumer cần dedup/idempotency theo stable event ID.

### Bài 6: Timeout thanh toán

`paymentGateway.charge(...)` timeout.

**Câu hỏi:** Có nên tự động đánh dấu `PAYMENT_FAILED`?

**Gợi ý:** Không nhất thiết. Request có thể đã xử lý ở gateway. Dùng `PAYMENT_UNKNOWN`, query status/webhook, retry với cùng idempotency key theo contract gateway.

### Bài 7: Retry sai

```java
for (int attempt = 0; attempt < 3; attempt++) {
    gateway.charge(
        amount,
        UUID.randomUUID().toString()
    );
}
```

**Câu hỏi:** Rủi ro và cách sửa?

**Gợi ý:** Mỗi lần dùng key khác có thể bị coi là charge mới. Dùng key cố định cho một payment attempt và logic retry có điều kiện.

### Bài 8: Tại sao không giữ SELECT FOR UPDATE khi publish?

Worker lock 100 outbox rows bằng SQL rồi gửi 100 HTTP requests trước COMMIT.

**Gợi ý:** Transaction/lock tồn tại trong suốt network calls, gây contention như anti-pattern ban đầu. Claim ngắn với lease, commit, publish ngoài DB transaction rồi mark kết quả ở transaction mới.

### Bài 9: Hai request cùng đặt hàng cuối

Tồn kho còn 1. Hai request cùng đọc stock=1 trước khi mở transaction rồi cùng đặt hàng.

**Câu hỏi:** Tách external call khỏi transaction đã đủ tránh oversell chưa?

**Gợi ý:** Chưa. Cần bảo vệ invariant bằng conditional update/locking/version/constraint trong transaction ngắn.

### Bài 10: Saga bị gián đoạn

Payment đã thành công, cập nhật Order=PAID thất bại vì DB outage.

**Câu hỏi:** Hệ thống khôi phục bằng cách nào?

**Gợi ý:** Có payment attempt ID và trạng thái bền vững, webhook/đối soát, retry update idempotent; nếu không thể hoàn tất thì compensation theo chính sách.

### Bài 11: Lazy loading sau transaction

Orchestrator nhận JPA Order đã detach rồi gọi `order.getCustomer().getEmail()` để gửi email.

**Câu hỏi:** Vì sao nguy hiểm và thay bằng gì?

**Gợi ý:** LAZY association có thể không tải được, hoặc giữ EntityManager lâu để tránh lỗi gây vấn đề mới. Transactional service trả DTO/payload cần thiết trước khi kết thúc context.

### Bài 12: @Transactional và self-invocation

Một `@Transactional` method được gọi từ một method khác cùng Spring bean mà không đi qua proxy.

**Câu hỏi:** Có thể tạo transaction đúng như mong đợi không?

**Gợi ý:** Trong proxy-based Spring thông dụng, self-invocation không áp dụng interceptor. Tách transactional service hoặc dùng cơ chế transaction đúng của framework.

### Bài 13: Cần bảo đảm gửi thông báo

Yêu cầu: “Sau khi đơn hàng commit, mọi đơn phải có một notification event được xử lý cuối cùng, kể cả khi app restart.”

**Câu hỏi:** Dùng AFTER_COMMIT callback đơn lẻ đủ không?

**Gợi ý:** Không. Transactional outbox + relay/retry với dedup consumer giải quyết khoảng trống crash sau commit tốt hơn.

### Bài 14: External read trước transaction

Service gọi tax API lấy quote, rồi mới tạo Invoice.

**Câu hỏi:** Quote có thể stale không?

**Gợi ý:** Có. Cần kiểm soát version/validity window và validate lại những invariant database cần nhất quán trong transaction.

### Bài 15: Thông số vận hành

Outbox backlog ngày càng tăng, DB transaction p95 vẫn thấp.

**Câu hỏi:** Có thể là lỗi ở đâu?

**Gợi ý:** Relay hoặc broker/gateway chậm/lỗi, lease/retry không đúng, consumer không theo kịp. Quan sát tuổi event, attempts, publish latency, số worker và dead-letter.

## 23. Bảng ghi nhớ cuối cùng

| Khái niệm | Điều cần nhớ |
|---|---|
| Database transaction | Atomic commit/rollback trong phạm vi tài nguyên DB được điều phối |
| External HTTP call | Không tự rollback theo database transaction |
| Long-running transaction | Có thể tăng lock wait, pool pressure và conflict |
| `EntityManager.flush()` | Đồng bộ SQL, **không commit** |
| `@Transactional` | Ranh giới transaction của framework, không biến HTTP thành XA |
| AFTER_COMMIT callback | Không chạy trước commit, nhưng không nhất thiết bền vững khi crash |
| Transactional outbox | Ghi dữ liệu nghiệp vụ và ý định gửi cùng DB transaction |
| Relay | Claim ngắn, gửi ngoài DB transaction, mark kết quả ở tx mới |
| At-least-once delivery | Có thể trùng event, cần idempotency |
| Idempotency key | Nhận diện một logical operation qua nhiều retry |
| Saga/state machine | Điều phối nhiều transaction cục bộ và compensation |
| Payment timeout | Có thể là UNKNOWN, không mặc định FAILED |
| Optimistic locking/constraint | Bảo vệ invariant khi concurrent requests |
| DTO/event payload | Không mang managed JPA entity/proxy sang process khác |
| Observability | Đo transaction duration, lock, pool, backlog, retry và unknown outcomes |

**Kết luận:** Khi một luồng JPA cần gọi hệ thống ngoài, hãy **giữ transaction database ngắn**, kết thúc phần thay đổi cần nguyên tử, rồi thực hiện network I/O ngoài transaction đó. Nhưng chỉ “chuyển HTTP ra ngoài `@Transactional`” chưa đủ với nghiệp vụ có side effect và yêu cầu không thất lạc: cần **trạng thái bền vững, retry, idempotency, đối soát và đôi khi compensation**. Với sự kiện cần được phát đáng tin cậy, **transactional outbox** giúp kết nối commit dữ liệu nghiệp vụ với công việc bên ngoài mà không giữ giao dịch DB mở trong lúc chờ mạng. Cách thiết kế này giảm tài nguyên bị giữ, hạn chế lỗi dây chuyền và làm trạng thái nghiệp vụ minh bạch hơn khi hệ thống phân tán gặp sự cố.
