# @TransactionalEventListener, xử lý sau commit và độ tin cậy của sự kiện

Trong ứng dụng Spring Data Relational JDBC, một use case thường ghi aggregate vào database rồi cần thực hiện thêm công việc: gửi email xác nhận, phát thông báo, cập nhật read model hoặc gửi message sang hệ thống khác. Nếu thực hiện công việc đó trước khi transaction commit, hệ thống có thể phát thông tin về một thay đổi cuối cùng bị rollback. Nếu chỉ chạy sau khi method service kết thúc, ta cũng chưa chắc transaction đã commit thành công.

`@TransactionalEventListener` cho phép gắn listener vào một giai đoạn cụ thể của transaction. Mặc định, listener chạy sau khi transaction commit thành công. Cách này hữu ích khi cần phản ứng với một thay đổi đã được lưu. Tuy nhiên, **chạy sau commit không đồng nghĩa với giao sự kiện đáng tin cậy**: process vẫn có thể dừng sau commit nhưng trước khi listener chạy, hoặc listener có thể thất bại sau khi dữ liệu đã commit.

Bài học giải thích cách publish event trong transaction, các phase của `@TransactionalEventListener`, hành vi lỗi và async, cách ghi dữ liệu tiếp theo bằng transaction mới, cùng transactional outbox để bảo đảm sự kiện không bị mất khi ứng dụng gặp sự cố.

## 1. Vì sao cần xử lý sự kiện sau commit?

Giả sử khách hàng đặt hàng. Service tạo aggregate đơn hàng, lưu root và các dòng hàng. Sau khi đơn được tạo, ứng dụng cần:

- Gửi email xác nhận.
- Cập nhật read model cho màn hình lịch sử đơn.
- Phát message cho dịch vụ giao hàng.
- Ghi nhận hoạt động vào một hệ thống phân tích.

Các công việc này phụ thuộc vào kết quả ghi đơn. Nếu đơn hàng chưa commit, một listener có thể gửi email hoặc message về một đơn hàng mà transaction cuối cùng không lưu lại.

Luồng không an toàn:

~~~text
BEGIN TRANSACTION
  save PurchaseOrder
  send OrderCreated to broker
  INSERT order_line -> constraint error
ROLLBACK

Broker đã nhận event nhưng đơn hàng không tồn tại.
~~~

Nếu listener chỉ được gọi sau khi commit:

~~~text
BEGIN TRANSACTION
  save PurchaseOrder
  publish application event
COMMIT
  |
  v
AFTER_COMMIT listener
  |
  +--> send email / update read model / notify
~~~

Khi transaction rollback, listener phase `AFTER_COMMIT` không chạy. Điều đó ngăn listener phản ứng với dữ liệu chưa được commit.

## 2. Application event và transactional event

Spring có cơ chế application event:

~~~java
publisher.publishEvent(new OrderCreated(orderId));
~~~

Một listener thông thường dùng `@EventListener`:

~~~java
@EventListener
public void onOrderCreated(OrderCreated event) {
    // xử lý ngay khi event được publish
}
~~~

`ApplicationEventPublisher.publishEvent` phát event trong luồng hiện tại. Với listener thông thường, phương thức listener được gọi trong quá trình publish; việc publish không tự đợi transaction commit.

`@TransactionalEventListener` đăng ký listener với transaction synchronization hiện tại để Spring gọi nó ở phase được chọn:

~~~java
@TransactionalEventListener
public void onOrderCreated(OrderCreated event) {
    // mặc định chạy sau commit
}
~~~

Mặc định phase là `TransactionPhase.AFTER_COMMIT`. Nếu không có transaction đang hoạt động, listener không được thực thi theo mặc định. Thuộc tính `fallbackExecution` có thể thay đổi hành vi này.

### 2.1. Event nên biểu diễn sự kiện đã xảy ra

Event thường dùng tên quá khứ để diễn đạt một sự kiện:

- `OrderCreated`.
- `OrderConfirmed`.
- `PaymentCaptured`.
- `InventoryReserved`.

Một event nên mang dữ liệu tối thiểu mà listener cần, thường gồm ID aggregate, event ID và một số giá trị bất biến cần thiết.

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderCreated(
        UUID eventId,
        Long orderId,
        String orderNumber,
        Instant occurredAt
) {
}
~~~

Dùng record giúp payload bất biến và dễ truyền giữa các thành phần. Không nên đưa toàn bộ entity/aggregate mutable vào event nếu listener chỉ cần ID; listener có thể tải dữ liệu mới nhất khi chạy. Nếu listener cần chính xác snapshot tại thời điểm event xảy ra, hãy đưa những giá trị snapshot cần thiết vào payload và xác định rõ semantics.

### 2.2. Publish event bên trong transaction

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            ApplicationEventPublisher events
    ) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public PurchaseOrder create(CreateOrderCommand command) {
        PurchaseOrder order = PurchaseOrder.create(
                command.orderNumber(),
                command.lines()
        );

        PurchaseOrder saved = orders.save(order);

        events.publishEvent(new OrderCreated(
                UUID.randomUUID(),
                saved.getId(),
                saved.getOrderNumber(),
                Instant.now()
        ));

        return saved;
    }
}
~~~

Điểm quan trọng là event được publish trong transaction của use case. `@TransactionalEventListener` nhận event và đợi phase tương ứng. Nếu `orders.save` hoặc một thao tác sau đó làm transaction rollback, listener AFTER_COMMIT không được gọi.

Đoạn code là ví dụ minh họa; kiểu ID và accessor cần khớp entity của dự án.

## 3. Các phase của @TransactionalEventListener

Annotation có thuộc tính `phase` để chọn thời điểm gọi listener:

| Phase | Khi nào listener chạy? | Trường hợp sử dụng |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction commit | Kiểm tra hoặc bổ sung thao tác cùng transaction trước commit |
| `AFTER_COMMIT` | Sau khi commit thành công | Gửi thông báo sau khi dữ liệu đã được lưu |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Ghi nhận/giải phóng tác vụ phụ thuộc vào rollback |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, dù commit hay rollback | Cleanup hoặc xử lý không phụ thuộc kết quả commit |

Ví dụ khai báo:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    // ...
}
~~~

`AFTER_COMMIT` là phase mặc định nếu không khai báo rõ.

### 3.1. BEFORE_COMMIT

Listener chạy trước khi transaction commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void validateOrderBeforeCommit(OrderCreated event) {
    // kiểm tra hoặc ghi thêm dữ liệu trong cùng transaction
}
~~~

Nếu listener ném unchecked exception trước commit, transaction có thể rollback theo cơ chế transaction của Spring. Phase này có thể dùng cho công việc phải hoàn tất trong transaction hiện tại.

Không dùng BEFORE_COMMIT để gửi email hoặc message ra hệ thống ngoài rồi kỳ vọng database rollback sẽ thu hồi side effect đó. Side effect bên ngoài database không tham gia transaction JDBC.

### 3.2. AFTER_COMMIT

Listener chỉ chạy khi transaction commit thành công:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendConfirmation(OrderCreated event) {
    emailService.sendOrderConfirmation(event.orderId());
}
~~~

Đây là lựa chọn thường gặp cho hành động phản ứng với dữ liệu đã commit. Tuy nhiên, listener chạy sau khi transaction đã hoàn tất. Nếu listener thất bại, database không thể rollback lại transaction vừa commit.

### 3.3. AFTER_ROLLBACK

Listener chỉ chạy sau rollback:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onOrderCreationRolledBack(OrderCreated event) {
    metrics.recordOrderCreationRollback(event.orderId());
}
~~~

Dùng phase này cho công việc hậu xử lý phù hợp với rollback, chẳng hạn metric hoặc thông tin quan sát. Không dùng nó để hoàn tác một side effect ngoài database nếu side effect đó lẽ ra không nên được phát trước commit.

### 3.4. AFTER_COMPLETION

Listener chạy sau khi transaction kết thúc, bất kể commit hay rollback:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void cleanup(OrderCreated event) {
    // cleanup không phụ thuộc transaction commit hay rollback
}
~~~

Phase này phù hợp cho cleanup hoặc công việc chỉ cần biết transaction đã hoàn tất. Nếu cần phân biệt kết quả, hãy dùng AFTER_COMMIT hoặc AFTER_ROLLBACK.

## 4. Không có transaction thì listener có chạy không?

Mặc định, `@TransactionalEventListener` chỉ được kích hoạt khi event được publish trong transaction đang hoạt động. Nếu không có transaction, listener không được gọi.

Ví dụ:

~~~java
public void publishWithoutTransaction() {
    events.publishEvent(new OrderCreated(...));
}
~~~

Nếu không có transaction, listener AFTER_COMMIT mặc định sẽ không chạy.

### 4.1. fallbackExecution

Có thể bật:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void onOrderCreated(OrderCreated event) {
    // chạy cả khi không có transaction để đăng ký synchronization
}
~~~

Khi không có transaction, listener được thực thi theo fallback behavior thay vì bị bỏ qua. Khi bật tùy chọn này, listener có thể chạy ngay trong quá trình publish vì không có transaction để chờ commit.

Chỉ bật nếu hành vi đó hợp lệ cho use case. Nếu listener phải bảo đảm dữ liệu đã commit trước khi chạy, việc publish ngoài transaction và fallback execution có thể phá vỡ giả định đó. Trong nhiều ứng dụng, giữ mặc định false giúp phát hiện nơi publish event sai transaction boundary.

## 5. Listener AFTER_COMMIT có chạy đồng bộ không?

Mặc định, listener được gọi đồng bộ trong luồng xử lý transaction completion. Khi commit hoàn tất, Spring gọi listener trước khi luồng xử lý trả kết quả về caller. Điều này có nghĩa:

- Listener có thể làm tăng latency của request.
- Exception từ listener có thể xuất hiện trong luồng gọi, dù transaction đã commit.
- Listener chạy lâu có thể giữ request thread lâu hơn.
- Listener không tự có retry bền vững.

Ví dụ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendEmail(OrderCreated event) {
    emailService.send(event.orderId()); // có thể mất vài giây
}
~~~

Dù email service lỗi, đơn hàng có thể đã commit. Caller có thể nhận lỗi trong khi dữ liệu đơn hàng vẫn tồn tại. Đây là lý do cần thiết kế response/retry cẩn thận.

## 6. Kết hợp @Async với @TransactionalEventListener

Nếu listener làm việc chậm, có thể chạy bất đồng bộ:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendConfirmation(OrderCreated event) {
    emailService.sendOrderConfirmation(event.orderId());
}
~~~

Khi event được xử lý ở AFTER_COMMIT, listener được giao cho executor theo cơ chế async. Request thread không cần chờ công việc hoàn tất, tùy cấu hình executor và cách Spring proxy phương thức.

### 6.1. Async không đồng nghĩa durable

Executor thường là thread pool trong bộ nhớ của process. Nếu ứng dụng dừng sau commit nhưng trước khi task được thực thi, event có thể mất. Nếu executor từ chối task vì queue đầy hoặc process crash, listener có thể không chạy.

Vì vậy:

- `@Async` giúp tách latency và thread execution.
- `@TransactionalEventListener` giúp chọn phase transaction.
- Cả hai không tự cung cấp durable queue, retry bền vững hoặc xác nhận delivery.

Nếu việc xử lý phải được thực hiện cuối cùng dù process restart, cần lưu công việc/sự kiện vào database hoặc broker có độ bền phù hợp, thường là transactional outbox.

### 6.2. Exception của async listener

Exception trong async task không thể quay lại transaction đã commit và thường không được ném về request thread như exception đồng bộ. Cần cấu hình logging, metric, error handler và retry phù hợp. Nếu chỉ ghi log, lỗi có thể bị bỏ qua mà không có cơ chế khôi phục.

### 6.3. Truyền dữ liệu và security context

Không giả định mọi thread-local context được truyền sang async executor. Nếu listener cần tenant, correlation ID, tracing hoặc security context, hãy truyền dữ liệu cần thiết trong event hoặc cấu hình task decorator/context propagation phù hợp. Không đưa credential nhạy cảm vào event payload.

## 7. Ghi database trong AFTER_COMMIT: cần transaction mới

Một điểm dễ gây lỗi: sau AFTER_COMMIT, transaction gốc đã commit, nhưng các resource JDBC có thể vẫn được bind cho quá trình completion callback. Nếu listener gọi repository để ghi thêm dữ liệu mà không mở transaction mới, thao tác có thể dùng resource đã hoàn tất và không được commit như mong đợi.

Nếu listener cần ghi database sau commit, hãy mở transaction mới:

~~~java
@Component
public class OrderReadModelListener {

    private final OrderReadModelService readModel;

    public OrderReadModelListener(OrderReadModelService readModel) {
        this.readModel = readModel;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void updateReadModel(OrderCreated event) {
        readModel.apply(event);
    }
}
~~~

Service ghi read model:

~~~java
@Service
public class OrderReadModelService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void apply(OrderCreated event) {
        // INSERT/UPDATE read model trong transaction mới
    }
}
~~~

`Propagation.REQUIRES_NEW` yêu cầu Spring tạo transaction độc lập cho thao tác này, thay vì tham gia transaction gốc đã commit. Phương thức phải được gọi qua Spring proxy; đặt service riêng giúp tránh self-invocation.

Lưu ý:

- Transaction mới không thể rollback transaction tạo đơn đã commit.
- Nếu read model update thất bại, đơn hàng vẫn tồn tại.
- Listener có thể cần retry hoặc cơ chế phục hồi nếu read model phải được cập nhật cuối cùng.
- Nếu công việc có yêu cầu độ tin cậy cao, outbox phù hợp hơn một callback trong bộ nhớ.

Không cần REQUIRES_NEW chỉ để đọc dữ liệu đã commit; lưu ý chủ yếu áp dụng khi listener cần ghi dữ liệu tiếp theo và phải bảo đảm commit độc lập.

## 8. Giới hạn độ tin cậy của AFTER_COMMIT

`@TransactionalEventListener` giải quyết **thời điểm xử lý tương đối với transaction**, không giải quyết việc lưu trữ event một cách bền vững.

Có một khoảng thời gian không thể loại bỏ chỉ bằng callback:

~~~text
Database COMMIT thành công
        |
        |  <-- process có thể crash tại đây
        v
Spring gọi AFTER_COMMIT listener
        |
        v
Listener xử lý side effect
~~~

Nếu process crash sau commit nhưng trước khi listener được gọi, dữ liệu nghiệp vụ đã tồn tại nhưng event chưa được xử lý. Không có bản ghi durable nào cho Spring biết cần chạy listener sau khi restart.

Một số failure mode:

| Failure | Hệ quả |
| --- | --- |
| Process chết ngay sau commit | Listener có thể chưa chạy |
| Listener ném exception | Business transaction vẫn đã commit |
| Async executor từ chối task | Công việc có thể không được thực thi |
| Async task đang chạy thì process chết | Công việc có thể dở dang |
| Gọi broker thành công nhưng process chết trước khi ghi nhận kết quả | Retry có thể phát event trùng |
| Gửi email thành công nhưng response từ email provider bị mất | Không biết chắc email đã gửi; retry có thể gửi lại |

Nếu nghiệp vụ chấp nhận best-effort notification, AFTER_COMMIT có thể đủ. Nếu không được phép mất event, cần một cơ chế durable.

## 9. Transactional outbox: lưu sự kiện cùng business change

Transactional outbox giải quyết khoảng trống giữa database commit và publish event:

1. Ghi aggregate.
2. Ghi một hàng outbox mô tả event.
3. Commit cả hai trong cùng database transaction.
4. Một publisher riêng đọc outbox và gửi event tới broker.
5. Publisher đánh dấu event đã gửi hoặc lưu trạng thái retry.

Sơ đồ:

~~~text
Application Service (@Transactional)
        |
        +-- save PurchaseOrder
        |
        +-- insert outbox_event
        |
        v
      COMMIT
        |
        v
Outbox Publisher / Worker
        |
        +-- read pending event
        |
        +-- publish to broker
        |
        +-- mark published
~~~

Nếu transaction rollback, cả aggregate và outbox row đều rollback. Nếu process chết sau commit, outbox row vẫn còn để publisher xử lý sau khi ứng dụng khởi động lại.

### 9.1. Bảng outbox

Ví dụ:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    payload TEXT NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    last_error TEXT
);

CREATE INDEX idx_outbox_pending
    ON outbox_event(published_at, next_attempt_at);
~~~

Schema production có thể cần trạng thái, lease owner, lease expiry, partition key hoặc version event. Payload có thể là JSON; kiểu cột và index cần điều chỉnh theo database.

### 9.2. Ghi outbox cùng aggregate

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            OutboxRepository outbox
    ) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public PurchaseOrder create(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(
                PurchaseOrder.create(command.orderNumber(), command.lines())
        );

        OrderCreated event = new OrderCreated(
                UUID.randomUUID(),
                saved.getId(),
                saved.getOrderNumber(),
                Instant.now()
        );

        outbox.insert(event);
        return saved;
    }
}
~~~

`orders.save` và `outbox.insert` phải dùng cùng datasource/transaction manager để bảo đảm cùng commit/rollback. Nếu outbox insert thất bại, transaction rollback cả đơn hàng.

### 9.3. Publisher gửi event

Một worker định kỳ hoặc tiến trình nền có thể lấy các event chưa publish:

~~~text
SELECT pending outbox rows
  -> publish event
  -> UPDATE published_at
~~~

Để nhiều publisher cùng chạy, cần cơ chế claim/lease hoặc locking phù hợp database. Một số database hỗ trợ `FOR UPDATE SKIP LOCKED` để các worker lấy các hàng khác nhau; cú pháp và semantics cần kiểm tra theo dialect.

Không giữ transaction database mở trong khi chờ broker lâu nếu có thể tránh. Một chiến lược thường dùng là claim event trong transaction ngắn, commit lease, publish, rồi cập nhật trạng thái trong transaction mới. Cần thiết kế lease timeout để phục hồi khi worker chết sau khi claim.

### 9.4. Outbox thường cung cấp at-least-once

Xét trường hợp:

1. Publisher gửi event thành công tới broker.
2. Broker xác nhận message.
3. Publisher chết trước khi cập nhật published_at.
4. Worker khởi động lại và gửi event đó lần nữa.

Vì vậy, outbox thường cung cấp **at-least-once delivery**. Event có thể được gửi nhiều lần. Consumer phải idempotent, ví dụ lưu event ID đã xử lý với unique constraint trong cùng transaction với thay đổi nghiệp vụ.

Không đánh dấu published trước khi gửi, vì nếu process chết sau khi đánh dấu nhưng trước khi gửi thì event bị mất. Gửi trước rồi đánh dấu có thể tạo duplicate, nên consumer deduplication là phần thiết yếu.

## 10. Vai trò của @TransactionalEventListener khi dùng outbox

Outbox là nguồn sự thật bền vững. `@TransactionalEventListener` vẫn có thể hữu ích để:

- Báo cho publisher trong cùng process rằng có event mới để xử lý sớm.
- Đánh thức worker thay vì đợi chu kỳ polling tiếp theo.
- Cập nhật metric hoặc cache best-effort sau commit.

Ví dụ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void wakeOutboxPublisher(OrderCreated event) {
    outboxWakeup.signal();
}
~~~

Nếu process crash trước khi wakeup, outbox row vẫn tồn tại và polling/worker sẽ xử lý sau. Vì vậy, wakeup chỉ là tối ưu latency; không phải nơi lưu event duy nhất.

## 11. Idempotency ở consumer

Outbox publisher có thể gửi trùng. Consumer cần lưu dấu event đã xử lý:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một transaction consumer:

1. Insert (consumer_name, event_id).
2. Nếu insert thành công, áp dụng thay đổi nghiệp vụ.
3. Commit cả dấu processed và thay đổi.
4. Nếu unique conflict, event đã được xử lý; không áp dụng lại.

Dấu processed và business write phải nằm trong cùng transaction. Nếu ghi dấu trước rồi business write thất bại nhưng vẫn commit dấu, event sẽ bị bỏ qua vĩnh viễn. Nếu business write commit trước rồi dấu processed thất bại, lần giao lại có thể áp dụng hiệu ứng lần nữa.

Đây là cùng nguyên tắc idempotency và unique constraint: database phải bảo vệ cả deduplication marker và thay đổi nghiệp vụ trong một transaction.

## 12. Thiết kế listener an toàn

Khi viết listener, cần trả lời:

- Listener có chỉ được chạy sau commit không?
- Nếu không có transaction, có nên bỏ qua event?
- Công việc có được phép thất bại mà không ảnh hưởng response request không?
- Listener có ghi database không; nếu có, cần transaction mới không?
- Công việc có thể chạy lại an toàn không?
- Process crash có được phép làm mất công việc không?
- Có cần outbox hoặc durable queue không?

Ví dụ listener best-effort:

~~~java
@Component
public class OrderNotificationListener {

    private final NotificationService notifications;

    public OrderNotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyCustomer(OrderCreated event) {
        notifications.sendOrderCreated(event.orderId());
    }
}
~~~

Ví dụ listener ghi database mới:

~~~java
@Component
public class OrderProjectionListener {

    private final OrderProjectionWriter writer;

    public OrderProjectionListener(OrderProjectionWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void project(OrderCreated event) {
        writer.apply(event);
    }
}
~~~

~~~java
@Service
public class OrderProjectionWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void apply(OrderCreated event) {
        // Ghi projection trong transaction mới.
    }
}
~~~

Nếu projection có thể được dựng lại từ bảng nguồn, có thể dùng job reconciliation để sửa sai lệch. Nếu việc phát event bắt buộc phải được giao, outbox đáng tin cậy hơn chỉ dựa vào listener.

## 13. Ordering và nhiều listener

Một event có thể có nhiều listener:

- Listener cập nhật read model.
- Listener gửi notification.
- Listener ghi metric.

Nếu cần thứ tự thực hiện giữa các listener đồng bộ, có thể dùng `@Order`:

~~~java
@Order(1)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void updateProjection(OrderCreated event) {
    // ...
}

@Order(2)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void notifyCustomer(OrderCreated event) {
    // ...
}
~~~

`@Order` sắp thứ tự listener trong cơ chế dispatch tương ứng; nó không tạo transaction chung cho các side effect sau commit và không bảo đảm thứ tự hoàn tất nếu listener chạy async. Nếu thứ tự nghiệp vụ quan trọng, hãy mô hình hóa dependency rõ ràng trong một handler hoặc workflow.

Với async listener, nhiều event có thể xử lý song song hoặc hoàn tất khác thứ tự. Nếu cần thứ tự theo aggregate, dùng sequence/version trong event và cơ chế partition/serialization ở publisher/consumer.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `@EventListener` cho công việc chỉ nên chạy sau commit | Listener có thể chạy trước khi transaction rollback | Dùng `@TransactionalEventListener` với AFTER_COMMIT |
| Publish event ngoài transaction nhưng mong listener đợi commit | Không có transaction để đăng ký synchronization | Publish bên trong use case transaction hoặc định nghĩa fallback rõ ràng |
| Bật `fallbackExecution` mà không xét semantics | Listener có thể chạy ngay khi không có transaction | Chỉ bật nếu xử lý ngoài transaction là hợp lệ |
| Nghĩ AFTER_COMMIT có thể rollback business write | Transaction đã commit trước listener | Thiết kế retry/compensation riêng |
| Listener ghi DB sau commit mà không mở transaction mới | Ghi có thể không được commit như mong đợi | Dùng `REQUIRES_NEW` qua Spring proxy |
| Nghĩ `@Async` làm event durable | Process crash có thể làm mất task trong bộ nhớ | Dùng outbox hoặc durable broker |
| Listener async lỗi nhưng chỉ log | Không có retry hoặc recovery | Error handler, retry, metric và outbox |
| Gửi message trước commit | Có thể phát event cho thay đổi rollback | Phát sau commit hoặc ghi outbox trong transaction |
| Nghĩ AFTER_COMMIT không thể mất event | Có crash window sau commit | Transactional outbox |
| Publisher đánh dấu sent trước khi gửi | Crash có thể làm mất event | Gửi rồi đánh dấu; chấp nhận duplicate và deduplicate consumer |
| Consumer không deduplicate | Event giao lại tạo hiệu ứng nhiều lần | Unique processed-event key trong transaction |
| Đưa entity mutable vào event | Listener nhận payload thay đổi hoặc phụ thuộc object lifecycle | Dùng event immutable với ID/snapshot cần thiết |
| Dựa vào `@Order` để bảo đảm async completion order | Listener có thể hoàn tất không theo thứ tự | Thiết kế workflow/partition theo aggregate |

## 15. Kiểm thử transactional event listener

Nên kiểm thử cả commit, rollback và trường hợp không có transaction.

### 15.1. Listener chạy sau commit

Một test integration:

1. Gọi service có `@Transactional`.
2. Service lưu aggregate và publish event.
3. Xác nhận listener được gọi sau commit.
4. Trong listener hoặc test probe, đọc lại aggregate để xác nhận dữ liệu đã commit.

Có thể dùng listener test hoặc spy tùy cấu trúc test. Tránh chỉ kiểm tra `publishEvent` được gọi vì điều đó không chứng minh phase listener hoạt động.

### 15.2. Listener không chạy khi rollback

Tạo một service test:

~~~java
@Transactional
public void createThenFail() {
    repository.save(order);
    events.publishEvent(new OrderCreated(...));
    throw new IllegalStateException("rollback");
}
~~~

Gọi method và xác nhận:

- Transaction rollback.
- Aggregate không tồn tại sau test.
- Listener AFTER_COMMIT không được gọi.
- Listener AFTER_ROLLBACK chỉ được gọi nếu có handler cho phase đó.

### 15.3. Test AFTER_COMMIT không rollback được business transaction

Cho listener ném exception sau commit. Xác nhận:

- Caller có thể quan sát exception tùy cơ chế dispatch.
- Aggregate vẫn tồn tại vì transaction đã commit.
- Không giả định lỗi listener sẽ undo dữ liệu.

Test này làm rõ ranh giới giữa business transaction và hậu xử lý.

### 15.4. Test REQUIRES_NEW

Listener gọi writer có `REQUIRES_NEW`; xác nhận dữ liệu projection được commit độc lập. Sau đó tạo lỗi ở một bước khác của listener và kiểm tra transaction mới rollback theo đúng ranh giới.

### 15.5. Test outbox và duplicate delivery

Kiểm tra:

- Aggregate và outbox row cùng commit.
- Khi business transaction rollback, outbox row không tồn tại.
- Publisher gửi event rồi crash trước khi đánh dấu published có thể gửi lại.
- Consumer nhận cùng event ID hai lần nhưng chỉ áp dụng business effect một lần.
- Worker có thể tiếp tục xử lý pending event sau khi restart.

Các test concurrency và dialect cần chạy trên database production hoặc Testcontainers phù hợp.

## 16. Quy trình chọn cơ chế xử lý sự kiện

Khi một use case cần phát event sau khi lưu aggregate:

1. **Xác định sự kiện:** mô tả fact đã xảy ra và dữ liệu listener cần.
2. **Publish trong transaction:** phát application event từ use case đang ghi aggregate.
3. **Chọn phase:** AFTER_COMMIT cho phản ứng sau khi dữ liệu được commit; BEFORE_COMMIT/AFTER_ROLLBACK/AFTER_COMPLETION chỉ khi semantics phù hợp.
4. **Quyết định sync hay async:** sync đơn giản nhưng tăng latency; async giảm thời gian chờ nhưng không durable.
5. **Nếu listener ghi DB:** mở transaction mới bằng REQUIRES_NEW khi cần commit độc lập.
6. **Đánh giá failure window:** process crash sau commit có được phép làm mất công việc không?
7. **Dùng outbox nếu cần độ tin cậy:** ghi event cùng aggregate trong một transaction.
8. **Thiết kế retry và deduplication:** event ID ổn định, consumer idempotent.
9. **Theo dõi vận hành:** log, metric, retry count, dead-letter hoặc trạng thái lỗi.
10. **Integration test:** commit, rollback, listener failure, restart/retry và duplicate delivery.

## Ghi nhớ

`@TransactionalEventListener` gắn việc xử lý event với vòng đời transaction. Mặc định `AFTER_COMMIT` chỉ chạy khi transaction commit thành công, nhờ đó listener không phản ứng với thay đổi đã rollback. Các phase BEFORE_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION phục vụ những nhu cầu khác nhau; `fallbackExecution` quyết định listener có chạy khi không có transaction hay không.

Sau commit, business transaction không thể bị listener rollback. Nếu listener cần ghi database, dùng transaction mới như `REQUIRES_NEW`. `@Async` tách công việc khỏi request thread nhưng chỉ dùng executor trong bộ nhớ nên không bảo đảm delivery khi process crash. Khi không được phép mất event, ghi outbox cùng aggregate trong transaction và dùng publisher/consumer có retry, deduplication bằng event ID. Như vậy, event được lưu bền vững cùng thay đổi nghiệp vụ, còn `@TransactionalEventListener` có thể đóng vai trò phản ứng nhanh sau commit.
