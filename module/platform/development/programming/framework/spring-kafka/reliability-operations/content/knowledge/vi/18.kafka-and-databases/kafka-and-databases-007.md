# Commit transaction thứ hai thất bại

Trong một dịch vụ Spring Kafka, nhiều luồng nghiệp vụ cần **vừa thay đổi dữ liệu trong database, vừa ghi hoặc xác nhận dữ liệu trên Kafka**. Ví dụ: lưu đơn hàng vào PostgreSQL rồi phát `OrderCreated`, hoặc đọc `PaymentCaptured`, cập nhật sổ cái và commit offset của consumer. Dễ có cảm giác rằng chỉ cần dùng `@Transactional` và cấu hình Kafka transaction thì cả hai thao tác sẽ hoặc cùng thành công hoặc cùng thất bại.

Thực tế, **database transaction và Kafka transaction là hai giao dịch riêng biệt**. Spring có thể điều phối thứ tự hoàn tất chúng bằng transaction synchronization hoặc các phương thức `@Transactional` lồng nhau. Nhưng điều phối **không đồng nghĩa một distributed transaction nguyên tử** giữa database và Kafka. Nếu transaction thứ nhất đã commit thành công, rồi transaction thứ hai commit thất bại, transaction thứ nhất **không thể được rollback ngược lại chỉ bằng exception**.

Đây là một trong những failure window quan trọng nhất của kiến trúc Kafka + database. Bài học giải thích trình tự xảy ra lỗi, hậu quả theo từng thứ tự commit, cách nhận diện kết quả không chắc chắn, và các kiến trúc phục hồi như transactional outbox, idempotent consumer, reconciliation và compensating action.

## 1. Hai transaction là hai ranh giới atomicity

Giả sử service xử lý command tạo đơn hàng:

```text
Client -> OrderService
            |
            +--> Database transaction
            |       INSERT orders
            |       COMMIT DB
            |
            +--> Kafka transaction
                    SEND OrderCreated
                    COMMIT KAFKA
```

Database có transaction log và cơ chế commit/rollback riêng. Kafka có transaction coordinator, transactional producer ID và commit/abort markers riêng. Một transaction manager của database không thể thu hồi một commit Kafka đã hoàn tất; một Kafka transaction manager cũng không thể tự hoàn tác một commit PostgreSQL đã được xác nhận.

| Thành phần | Atomicity thực sự được cung cấp |
|---|---|
| Database transaction | Các thay đổi thuộc cùng transaction của database đó |
| Kafka producer transaction | Các record Kafka và, trong kịch bản phù hợp, consumer group offsets được đưa vào cùng Kafka transaction |
| Spring transaction synchronization | Phối hợp vòng đời và thứ tự hoàn tất các transaction riêng |
| Hai `@Transactional` với hai manager | Hai transaction cục bộ, có thứ tự thực thi; không tự tạo distributed atomic commit |
| Transactional outbox | Đồng bộ thay đổi nghiệp vụ và ý định phát event **trong một DB transaction**; xuất bản Kafka là bước riêng có retry và deduplication |

**Nguyên tắc nền tảng:** một lần commit thành công đã tạo ra hiệu lực bền vững trong resource thứ nhất. Exception ở bước commit thứ hai chỉ thông báo rằng toàn bộ *quy trình liên tài nguyên* không đạt mục tiêu, chứ không tự hoàn nguyên resource thứ nhất.

## 2. Hai thứ tự commit và hai kiểu mất nhất quán

Không có một thứ tự commit nào xóa được failure window. Thay đổi thứ tự chỉ thay đổi **bên nào có thể đi trước bên còn lại**.

### 2.1. Database-first: database commit trước, Kafka commit sau

```text
BEGIN DB
   |
   +--> INSERT orders
   |
   +--> KafkaTemplate.send(OrderCreated) trong Kafka transaction
   |
COMMIT DB                           [THÀNH CÔNG]
   |
COMMIT KAFKA                        [THẤT BẠI]
   |
   v
Database có Order; event có thể không xuất hiện như đã commit
```

Ở trạng thái này, một đơn hàng có thể tồn tại trong database nhưng không có `OrderCreated` được consumer `read_committed` nhìn thấy. Nếu downstream chỉ dựa vào event, nó không biết đơn hàng đã tạo; cache, search index, shipping hoặc billing có thể bị thiếu thông tin.

Nếu Kafka commit bị timeout hoặc mất kết nối, kết quả còn có thể **không xác định** tại thời điểm ứng dụng nhận exception: broker đã commit nhưng response không tới client, hoặc commit chưa thành công. Không nên mặc định mọi `commitTransaction()` exception đều chứng minh event hoàn toàn không tồn tại.

### 2.2. Kafka-first: Kafka commit trước, database commit sau

```text
BEGIN DB
   |
   +--> Thay đổi orders (chưa commit)
   |
BEGIN KAFKA
   |
   +--> SEND OrderCreated
   |
COMMIT KAFKA                        [THÀNH CÔNG]
   |
COMMIT DB                           [THẤT BẠI]
   |
   v
Consumer có thể thấy OrderCreated; database chưa chắc có Order
```

Đây là trạng thái **event đã công bố nhưng trạng thái nguồn chưa commit**. Một downstream listener có thể nhận event rất nhanh rồi truy vấn order ID không tồn tại, hoặc kích hoạt một nghiệp vụ dựa trên một thay đổi DB không xảy ra. Kafka-first không phải cách đảm bảo atomicity; nó đơn giản là chọn chiều bất nhất khác.

### Bảng so sánh

| Thứ tự | Transaction thứ nhất | Transaction thứ hai thất bại | Dấu hiệu nguy hiểm |
|---|---|---|---|
| DB → Kafka | Database đã commit | Kafka commit lỗi/không chắc chắn | Có dữ liệu DB, event có thể thiếu |
| Kafka → DB | Kafka đã commit | Database commit lỗi/không chắc chắn | Event có thể đã phát, dữ liệu DB thiếu |

Việc chọn thứ tự có thể tối ưu cách phục hồi trong một nghiệp vụ cụ thể, nhưng nếu yêu cầu không được phép mất event hoặc phát event không có trạng thái nguồn, hãy cân nhắc **outbox** thay vì dựa vào thứ tự commit.

## 3. Spring Kafka đồng bộ Kafka transaction với DB transaction

Spring Kafka có thể đồng bộ một Kafka transaction với một transaction do `DataSourceTransactionManager` hoặc transaction manager DB quản lý. Khi phương thức `@Transactional` dùng DB làm transaction chính và `KafkaTemplate` dùng transactional producer, thông thường **DB commit trước, Kafka commit sau**.

Ví dụ cấu hình nền tảng:

```properties
# Producer cần transactional.id prefix để tạo Kafka transaction.
# Mỗi instance đang chạy đồng thời phải có phạm vi ID riêng.
spring.kafka.producer.transaction-id-prefix=order-service-instance-a-

spring.kafka.producer.acks=all
spring.kafka.consumer.enable-auto-commit=false
```

Đối với ứng dụng nhiều replica, `order-service-instance-a-` chỉ là placeholder minh họa. Mỗi instance đồng thời phải được cấp prefix/transactional ID không xung đột; nếu không, producer có thể bị fenced. Ngoài ra, Kafka producer factory, serializer, broker và topic phải hỗ trợ giao dịch theo cấu hình hiện hành.

Ví dụ một service sử dụng DB transaction làm transaction chính:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderApplicationService(
            OrderRepository orderRepository,
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("dataSourceTransactionManager")
    public void createOrder(CreateOrder command) {

        Order order = orderRepository.save(
                Order.fromCommand(command));

        OrderCreated event = new OrderCreated(
                command.eventId(), order.getId(), order.getStatus());

        // Transactional KafkaTemplate tham gia synchronization.
        kafkaTemplate.send("orders-events", order.getId(), event);
    }
}
```

Mã giả định `dataSourceTransactionManager` là bean quản lý DB transaction, `KafkaTemplate` sử dụng transactional `ProducerFactory`, và các class domain do ứng dụng định nghĩa. Ở cấu hình transaction synchronization phù hợp, lệnh `send()` được thực hiện trong Kafka transaction và Kafka transaction được commit sau DB transaction.

**Điểm quan trọng:** lệnh `send()` trả future không đồng nghĩa Kafka transaction đã commit. Ngay cả khi broker nhận record trong một transaction đang mở, consumer `read_committed` chỉ được thấy record sau commit. Nếu Kafka commit thất bại sau khi DB đã commit, DB vẫn giữ thay đổi.

Trong các phiên bản Spring Kafka hiện đại, lỗi commit của transaction được đồng bộ sau khi transaction chính đã commit được báo cho caller. Ở một số bản phát hành cũ, cách báo lỗi của synchronized commit khác nhau. Vì vậy, cần xác nhận dependency version và không coi việc caller nhận exception là bằng chứng DB đã rollback.

## 4. Commit thứ hai thất bại: trạng thái thực tế không chỉ có một

Đội vận hành thường nói ngắn gọn “Kafka commit failed”, nhưng có ba tình huống quan sát khác nhau:

1. **Chắc chắn không commit:** transaction đã abort hoặc có kết quả rõ ràng rằng commit không được chấp nhận.
2. **Commit thành công:** Kafka đã lưu commit marker và producer/client nhận xác nhận.
3. **Kết quả chưa chắc chắn:** commit request hoặc response bị gián đoạn; client nhận timeout/network exception nhưng chưa đủ bằng chứng để khẳng định transaction đã hay chưa commit.

Điều tương tự có thể xảy ra ở database: connection bị mất vào đúng thời điểm `COMMIT`, khiến caller không biết DB đã chấp nhận commit hay chưa. Vì vậy, không nên chỉ nhìn loại exception để quyết định lặp lại toàn bộ thao tác.

```text
Application                  Kafka coordinator
     |                             |
     |------ commitTransaction --> |
     |                             |  có thể xử lý commit
     |         X network           |
     |<---- không nhận response --- |
     |
     v
Application báo lỗi; trạng thái thực tế cần đối soát
```

Với Kafka producer transactional, không cố tiếp tục tái sử dụng một producer đang ở trạng thái lỗi nghiêm trọng theo cách không được client cho phép. Hãy để transaction manager thực hiện abort/close/fencing recovery phù hợp. Việc một producer mới dùng transactional ID tiếp theo có thể fence producer cũ nhưng **không tự suy luận hoặc sửa** bất nhất giữa Kafka và database đã xảy ra trước đó.

## 5. Vì sao `try/catch` không thể rollback commit đã hoàn tất?

Một đoạn code kiểu sau thường gây ngộ nhận:

```java
try {
    orderRepository.save(order);
    kafkaTemplate.send("orders-events", order.getId(), event);
}
catch (Exception ex) {
    // Sai nếu cho rằng DB chắc chắn đã rollback.
    throw ex;
}
```

`throw ex` có thể đánh dấu rollback khi **DB transaction vẫn đang mở**. Nhưng trong kịch bản Kafka commit được đồng bộ **sau DB commit**, exception có thể xuất hiện khi database đã hoàn tất commit. Không có transaction DB còn mở để rollback nữa.

Gọi `orderRepository.delete(order)` như bước bù trừ tự động cũng không có bảo đảm trả hệ thống về trạng thái cũ. Các tác vụ khác có thể đã nhìn thấy order, foreign key hoặc audit có thể đã được ghi, và lệnh delete có thể lại thất bại. Nếu cần compensation, đó phải là **một nghiệp vụ có định nghĩa riêng** với dấu vết kiểm toán và khả năng thử lại, không phải thao tác hoàn tác ngầm.

## 6. Đảo thứ tự: Kafka-first bằng nested transactions

Khi cần Kafka commit trước DB, Spring Kafka cho phép sử dụng các phương thức `@Transactional` lồng nhau với **hai transaction manager khác nhau**, trong đó phương thức ngoài dùng DB manager, còn phương thức trong dùng Kafka manager.

```java
@Service
public class KafkaOrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public KafkaOrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders-events", event.orderId(), event);
    }
}
```

Phương thức ngoài:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final KafkaOrderEventPublisher eventPublisher;

    public OrderService(
            OrderRepository orderRepository,
            KafkaOrderEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional("dataSourceTransactionManager")
    public void createOrder(CreateOrder command) {
        Order order = orderRepository.save(Order.fromCommand(command));
        eventPublisher.publish(new OrderCreated(
                command.eventId(), order.getId(), order.getStatus()));
        // DB commit khi phương thức ngoài kết thúc.
    }
}
```

Trong luồng này, lời gọi `eventPublisher.publish(...)` đi qua Spring proxy của **một bean khác** nên transaction Kafka của phương thức trong có thể bắt đầu và commit trước khi DB transaction ngoài kết thúc. Nếu đặt hai method trong cùng class và gọi `this.publish(...)`, self-invocation có thể bỏ qua proxy `@Transactional`, làm thứ tự thực tế khác dự tính.

Thiết kế này **không xử lý được** trường hợp `eventPublisher.publish()` đã commit Kafka thành công nhưng DB commit sau đó thất bại. Record `OrderCreated` có thể đã visible với downstream, trong khi `orders` chưa có bản ghi tương ứng. Chỉ đảo thứ tự khi đã có lý do nghiệp vụ và kế hoạch xử lý trạng thái này.

### Không nhầm `KafkaTransactionManager` với XA

`KafkaTransactionManager` điều phối transaction của Kafka producer. `DataSourceTransactionManager` điều phối transaction JDBC. Việc một class sử dụng hai annotation `@Transactional` không biến chúng thành hai participant của một XA two-phase commit. Một số cách ghép transaction manager cũ, chẳng hạn `ChainedKafkaTransactionManager`, đã bị deprecated trong các dòng Spring Kafka tương ứng; dù có coordinator thực hiện commit tuần tự, vẫn phải xử lý được partial commit nếu manager thứ hai lỗi.

## 7. Kafka consumer → database: transaction thứ hai cũng có thể lỗi

Failure window không chỉ xuất hiện khi một REST service viết DB rồi publish event. Nó cũng có thể xảy ra ở một listener xử lý record đến từ Kafka:

```text
Kafka consumer nhận PaymentCaptured
          |
          v
Kafka listener container bắt đầu Kafka transaction
          |
          v
@Transactional(DB) cập nhật ledger và inbox
          |
          v
DB COMMIT                         [thành công]
          |
          v
Kafka transaction commit
  (offset hoặc output + offset)    [thất bại]
          |
          v
Record nguồn có thể được giao lại sau restart/rebalance
```

Khi listener được gọi bên trong Kafka transaction do container quản lý, một phương thức nghiệp vụ `@Transactional` riêng có thể commit database trước khi container commit Kafka transaction. Nếu Kafka commit lỗi, **database đã có side effect**, nhưng group offset có thể chưa được ghi nhận. Trong lần delivery tiếp theo, cùng `PaymentCaptured` có thể được xử lý lại.

Nếu consumer chỉ làm thao tác DB, thường không cần bật Kafka transaction chỉ để có một consumer “exactly once” với DB. Một phương án dễ hiểu hơn là **DB transaction có inbox/idempotency + consumer offset commit sau DB commit**, chấp nhận at-least-once delivery. Như vậy, replay không làm nghiệp vụ nhân đôi.

Ví dụ listener và service idempotent:

```java
@KafkaListener(topics = "payments", groupId = "ledger-service")
public void onPayment(PaymentCaptured event) {
    ledgerService.applyOnce(event);
}

@Service
public class LedgerService {

    private final ProcessedEventRepository processed;
    private final LedgerRepository ledger;

    @Transactional("dataSourceTransactionManager")
    public void applyOnce(PaymentCaptured event) {
        // processed_event.event_id có UNIQUE constraint trong database.
        if (processed.insertIfAbsent(event.eventId())) {
            ledger.credit(event.accountId(), event.amount());
        }
    }
}
```

`insertIfAbsent` trong ví dụ biểu diễn thao tác insert atomic vào bảng có unique constraint; không nên tự viết kiểu “SELECT xem tồn tại rồi INSERT” mà không bảo vệ race condition. Insert marker và cập nhật ledger phải thuộc **cùng DB transaction**. Nếu DB commit thành công nhưng Kafka offset commit thất bại, redelivery sẽ gặp cùng event ID và bỏ qua side effect trùng.

## 8. Transactional outbox: giải pháp ưu tiên cho DB → Kafka

Nếu một thao tác **phải đảm bảo trạng thái DB và ý định phát event cùng được lưu**, transactional outbox thường là lựa chọn bền vững hơn việc commit tuần tự DB và Kafka trong cùng request.

Thay vì gửi Kafka trực tiếp trong transaction DB, lưu một outbox row ngay trong **cùng DB transaction** với thay đổi nghiệp vụ:

```text
Client / command
     |
     v
BEGIN DATABASE TRANSACTION
     |
     +--> INSERT/UPDATE orders
     |
     +--> INSERT outbox_events
     |
COMMIT DATABASE TRANSACTION
     |
     v
Outbox relay (polling hoặc CDC)
     |
     v
Publish Kafka OrderCreated
     |
     v
Mark outbox as published / advance CDC position
```

Nếu DB commit thất bại, cả order lẫn outbox row đều không xuất hiện. Nếu DB commit thành công nhưng Kafka unavailable, outbox row **vẫn còn** để retry khi Kafka hồi phục. Lúc này không còn một cửa sổ “DB đã commit nhưng mất ý định phát event”. Relay có thể trì hoãn, nhưng không phụ thuộc một request thread còn sống để giữ sự kiện trong RAM.

### Ví dụ schema đơn giản

```sql
CREATE TABLE orders (
    id              VARCHAR(64) PRIMARY KEY,
    request_id      VARCHAR(80) NOT NULL UNIQUE,
    status          VARCHAR(32) NOT NULL
);

CREATE TABLE outbox_events (
    event_id        UUID PRIMARY KEY,
    aggregate_id    VARCHAR(64) NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload_json    JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ NULL
);
```

Ví dụ cho PostgreSQL; database khác cần kiểu dữ liệu/cú pháp riêng. `request_id` giúp chống tạo order trùng khi client retry request; `event_id` là định danh bền vững dùng để deduplicate event giữa các lần relay publish.

### Ví dụ lưu order và outbox trong một DB transaction

```java
@Service
public class PlaceOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional("dataSourceTransactionManager")
    public void place(PlaceOrder command) {
        Order order = orders.insertIfAbsent(command.requestId(), command);

        outbox.insertIfAbsent(
                order.createdEventId(),
                order.id(),
                "OrderCreated",
                serializeEvent(order));
    }
}
```

`insertIfAbsent`, `createdEventId` và `serializeEvent` là nghiệp vụ/phương thức minh họa, không phải API mặc định của Spring Data. Khi request bị retry, cần tạo `event_id` ổn định hoặc suy ra từ một khóa nghiệp vụ idempotent; nếu lần retry lại tạo một UUID mới và insert thêm outbox row, vẫn có thể phát event trùng.

### Tại sao outbox vẫn cần idempotency?

Giả sử relay publish event lên Kafka thành công nhưng crash **trước khi đặt `published_at`**. Khi chạy lại, relay thấy outbox row chưa được đánh dấu và publish thêm một lần. Vì thế outbox giải quyết **không đánh mất ý định phát**, nhưng có thể gửi trùng. Consumer phải deduplicate theo `event_id`; relay có thể dùng Kafka producer idempotence, song idempotent producer không loại bỏ mọi duplicate của hai lần publish logic khác nhau.

Outbox relay có thể dùng polling với `FOR UPDATE SKIP LOCKED` và backoff, hoặc change-data-capture (CDC) đọc database log. Chọn cách nào cũng cần monitoring outbox backlog, publish latency, poison events và chiến lược resume.

## 9. Inbox + outbox cho luồng Kafka → DB → Kafka

Khi listener vừa cập nhật DB vừa tạo một event Kafka mới, có thể kết hợp **transactional inbox** và **transactional outbox** trong cùng DB transaction:

```text
Kafka input record (eventId = E123)
              |
              v
BEGIN DB TRANSACTION
              |
              +--> INSERT inbox(E123) với UNIQUE constraint
              |
              +--> UPDATE domain state
              |
              +--> INSERT outbox(EventDerivedFromE123)
              |
COMMIT DB TRANSACTION
              |
              v
Container commit Kafka input offset (có thể thất bại)

Outbox relay --> Kafka output
```

Nếu Kafka input offset commit thất bại, record sẽ được giao lại. Khi đó `inbox(E123)` đã tồn tại nên service nhận diện đã xử lý, **không cập nhật DB lần nữa và không tạo outbox event thứ hai**. Outbox relay đảm bảo ý định publish output vẫn còn khi Kafka chưa sẵn sàng. Đây là một mô hình triển khai at-least-once + idempotency rất hữu ích khi hai resource không có distributed atomicity.

Nên dùng Kafka key đúng aggregate để giữ ordering theo partition nếu cần; nhưng outbox/relay cũng phải duy trì thứ tự của các event cùng aggregate. Nếu nhiều relay worker lấy outbox theo thứ tự không ổn định, có thể phát `OrderShipped` trước `OrderCreated`. Điều này cần được giải quyết trong relay design, không phải chỉ bằng DB unique constraint.

## 10. Giao dịch thứ hai lỗi nhưng kết quả không chắc chắn: phải đối soát

Khi log ghi `commitTransaction failed`, runbook không nên lập tức “send lại event”. Nếu commit thực ra đã thành công nhưng response bị mất, send lại có thể tạo duplicate. Cần đối soát bằng những khóa có thể kiểm chứng:

- **Database:** tra cứu order/transaction theo request ID, aggregate ID, event ID hoặc phiên bản state đã được commit.
- **Kafka:** dùng consumer `read_committed` hoặc audit/index có hỗ trợ để xác nhận event ID đã xuất hiện dưới dạng record đã commit. Việc tìm một event theo key trong Kafka log có thể tốn chi phí; nên chuẩn bị khả năng kiểm chứng từ trước.
- **Outbox:** xác nhận outbox row tồn tại, published marker/checkpoint và số lần publish/ack.
- **Consumer downstream:** tra cứu inbox/event processing ledger để biết side effect đã hoàn tất hay chưa.

Một record tìm thấy trên Kafka không tự chứng minh state DB đúng; một row DB tồn tại không tự chứng minh event Kafka đã commit. Kết luận phải dựa trên **cả hai vế** và định nghĩa bất biến nghiệp vụ.

Ví dụ bảng đối soát:

| DB state | Kafka event đã commit | Hành động cần xem xét |
|---|---|---|
| Có | Có | Xác nhận downstream đã xử lý; tránh publish lặp không cần thiết |
| Có | Không | Phát event bù/missing event bằng job có idempotency; nên dựa vào outbox |
| Không | Có | Điều tra ghost event, chọn compensating event hoặc phục hồi state nếu nghiệp vụ cho phép |
| Không | Không | Kiểm tra request thất bại/chưa commit; retry request theo khóa idempotent nếu phù hợp |
| Chưa xác định | Chưa xác định | Tạm dừng thao tác gây side effect mới, bổ sung bằng chứng và escalation |

Không giả định hai cột có thể được xác nhận tuyệt đối chỉ bằng một log producer: các lần publish khác, retention, compaction và schema khiến phép tìm kiếm có thể phức tạp. Mục tiêu là thiết kế hệ thống **có thể reconciliation** ngay từ đầu.

## 11. Compensation: khi không thể undo commit đầu tiên

Khi Kafka-first tạo event đã visible nhưng DB commit thất bại, hệ thống có thể phải phát một **compensating event** như `OrderCreationCancelled` hoặc chuyển workflow sang trạng thái `FAILED_REQUIRES_RECONCILIATION`. Compensation nên biểu diễn một hành động nghiệp vụ mới thay vì cố xóa lịch sử Kafka.

```text
OrderCreated đã phát trên Kafka
             |
             v
DB commit thất bại
             |
             v
Reconciliation phát hiện thiếu Order trong DB
             |
             v
OrderCreationCancelled / compensation workflow
             |
             v
Downstream idempotently áp dụng trạng thái bù
```

Compensation có thể thất bại hoặc đến chậm, vì vậy nó cần retry, idempotency, correlation ID và monitoring riêng. Nếu downstream đã thực hiện tác vụ không thể hoàn tác (ví dụ gửi email, thực hiện chuyển tiền), một event bù không khiến tác vụ đó biến mất. Hãy xác định rõ phạm vi có thể bù trừ trước khi chọn Kafka-first.

Với DB-first và missing Kafka event, sự kiện phát bù thường là **event thể hiện trạng thái DB hiện tại**, có stable ID và provenance để không gây duplicate khi Kafka commit ban đầu thực ra đã thành công. Outbox giúp tránh phải suy luận event thiếu dựa trên so sánh hai hệ thống sau sự cố.

## 12. Vai trò của retry, DLT và `DefaultErrorHandler`

Retry và Dead Letter Topic (DLT) xử lý **record tiêu thụ lỗi**; chúng không tự sửa một partial commit giữa DB và Kafka. Ví dụ listener đã commit DB nhưng Kafka transaction commit offset lỗi, rồi record được giao lại. Nếu listener không idempotent, dù retry thành công hay về DLT, DB vẫn có thể bị cập nhật hai lần.

`DefaultErrorHandler` và `DeadLetterPublishingRecoverer` nên tập trung vào exception classification, backoff và lưu record không thể xử lý. Khi exception xảy ra sau khi DB đã commit, không được tự động kết luận rằng retry toàn bộ business method là an toàn.

Một DLT có thể hữu ích cho:

- Tạm cách ly event khi consumer không thể xử lý.
- Lưu original topic/partition/offset và exception để điều tra.
- Hỗ trợ replay có kiểm soát sau khi sửa lỗi và bảo vệ idempotency.

Nhưng DLT **không phải** kho bảo đảm mọi thay đổi DB có event Kafka tương ứng. Trong DB-first, transaction thứ hai thất bại có thể xảy ra ở một request publisher trước khi có bất kỳ consumer record hay DLT nào. Trường hợp đó cần outbox hoặc reconciliation riêng.

Ngoài ra, nếu DLT publisher itself dùng transaction, việc commit DLT và offset nguồn vẫn phải được cấu hình đúng để tránh mất record/duplicate. “Record đã được gửi sang DLT” không đồng nghĩa một commit DB trước đó có thể bị thu hồi.

## 13. Quy tắc xử lý exception sau khi transaction thứ nhất commit

Khi framework báo lỗi sau commit thứ nhất, phản ứng an toàn thường là:

1. **Không nói với caller rằng mọi thay đổi đều đã rollback.** HTTP 500 chỉ cho biết request không hoàn tất như mong muốn; không chứng minh DB không có dữ liệu.
2. **Không retry mù quáng toàn bộ command.** Đầu vào cần idempotency key và logic nhận diện trạng thái đã thực hiện.
3. **Đánh dấu kết quả chưa chắc chắn**, ví dụ `PENDING_RECONCILIATION`, nếu hệ thống hỗ trợ trạng thái này.
4. **Ghi log/audit correlation ID** và identifier bền vững để truy vết hai resource.
5. **Chạy reconciliation hoặc outbox relay** với retry có giới hạn và alert khi quá thời gian.
6. **Chỉ compensation khi nghiệp vụ định nghĩa rõ**, không cố thủ công xóa dữ liệu đã commit.

Các HTTP API có thể chọn trả `202 Accepted` cùng request ID khi một thao tác bất đồng bộ chưa hoàn tất, hoặc trả lỗi có mã cho phép client tra trạng thái. Nhưng trạng thái trả về phải phản ánh workflow thật; không trả “failed” nếu DB đã commit mà hệ thống không có cơ chế nhận diện và xử lý trùng khi client gửi lại.

Đối với API tạo order, `request_id` unique và endpoint truy vấn trạng thái theo request ID là công cụ quan trọng để tránh tạo hai đơn hàng khi caller retry sau timeout.

## 14. Quan sát và runbook khi commit thứ hai thất bại

Chỉ số cần theo dõi không dừng ở Kafka producer errors. Nên thiết kế metric và alert cho **khoảng cách giữa hai hệ thống**:

| Metric / dấu vết | Mục đích |
|---|---|
| DB transaction success/error | Biết thao tác chính đã commit hay chưa |
| Kafka transaction commit/abort/timeout | Phát hiện failure window và producer fencing |
| Outbox unpublished count và oldest age | Nhận biết DB đã lưu ý định phát nhưng Kafka chưa nhận được |
| Relay publish attempts, success, duplicate | Phân biệt backlog bình thường và phát trùng |
| Inbox duplicate rate | Đo mức redelivery và hiệu quả idempotent consumer |
| Consumer lag, offset commit errors | Phát hiện input có thể được giao lại sau side effect DB |
| Reconciliation mismatch count | Nhận biết DB có event thiếu hoặc Kafka có ghost event |
| Compensation pending/failed | Theo dõi nghĩa vụ sửa bất nhất chưa hoàn tất |

Runbook đề xuất:

1. Ghi nhận chính xác transaction nào commit đầu tiên và manager nào báo lỗi.
2. Xác định `requestId`, `eventId`, `orderId`, topic, partition, offset và transaction ID nếu có.
3. Kiểm tra transaction thứ nhất đã được xác nhận commit hay chưa; không suy luận từ exception của transaction thứ hai.
4. Kiểm tra Kafka transaction state/record visibility bằng consumer `read_committed` hoặc audit được thiết kế trước.
5. Xác nhận có outbox/inbox row và side effect downstream hay không.
6. Tạm ngăn replay hàng loạt trong khi kết quả commit còn chưa rõ.
7. Áp dụng reconciliation, publish thiếu hoặc compensation theo runbook nghiệp vụ.
8. Giám sát đến khi hai hệ thống đạt trạng thái thống nhất, ghi nhận root cause và chỉnh sửa thiết kế nếu cần.

Trong khi xử lý sự cố, không tự ý reset consumer group offsets để “sửa” thiếu event. Reset lùi có thể nhân đôi side effect; reset tiến có thể bỏ qua record chưa xử lý. Commit offset và event publish là hai nhánh trạng thái khác nhau cần kiểm chứng riêng.

## 15. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách tiếp cận |
|---|---|---|
| API trả 500 nhưng order đã tồn tại | DB commit thành công, Kafka synchronized commit lỗi | Dùng request ID để truy trạng thái; outbox/reconciliation thay vì tạo order mới |
| Event Kafka tồn tại nhưng DB không có order | Kafka-first commit thành công, DB commit lỗi | Đối soát, compensation hoặc điều chỉnh kiến trúc sang outbox |
| Một payment bị ghi ledger hai lần | DB commit trước, Kafka offset commit lỗi, record được giao lại | Inbox/unique constraint và DB transaction bao cả marker lẫn side effect |
| Event xuất hiện trùng sau retry | Publish thực ra commit rồi nhưng response timeout; caller publish lại | Stable event ID và idempotent downstream; không đồng nhất producer idempotence với business deduplication |
| DB-first nhưng ứng dụng tưởng đã rollback hết | Exception xảy ra sau DB commit | Log hai giai đoạn commit, báo trạng thái chưa chắc chắn |
| Kafka transaction bị fenced khi scale | Nhiều instance cùng transactional ID hoặc producer cũ chưa bị thay thế đúng | Cấp transactional ID/prefix đúng phạm vi instance; quan sát fencing |
| Outbox tăng không giảm | Kafka outage, relay lỗi serializer/ACL hoặc poison payload | Alert oldest age, retry có backoff, DLT/quarantine cho relay và điều tra |
| Reconciliation chạy lại gây phát event trùng | Không có idempotency hoặc job checkpoint không bền vững | Dùng stable event ID và deduplication theo business key |
| Hai `@Transactional` không đảo commit như kỳ vọng | Self-invocation bypass Spring proxy hoặc chọn sai manager | Đặt method trong bean khác, ghi rõ transaction manager và kiểm chứng flow |

## 16. Kịch bản kiểm thử tích hợp cho failure window

Để chứng minh hệ thống chịu được commit thứ hai thất bại, cần chủ động tạo các sự cố tại các ranh giới transaction. Có thể dùng Testcontainers cho Kafka và database, thêm fault injection ở producer/DB/network hoặc một adapter test có kiểm soát. Không chỉ mock `KafkaTemplate.send()` rồi kết luận đã kiểm tra commit: lỗi có thể xảy ra **sau khi send future hoàn tất**, tại `commitTransaction()`.

Các kịch bản đáng có:

1. **DB-first thành công:** DB có row, Kafka có event đã commit, downstream xử lý một lần về mặt nghiệp vụ.
2. **DB-first Kafka commit thất bại:** DB vẫn có row; job reconciliation/outbox có cách đảm bảo event cuối cùng được xuất bản.
3. **Kafka-first DB commit thất bại:** Kafka event có thể đã visible; compensation hoặc đối soát phát hiện bất nhất.
4. **Timeout đúng lúc commit Kafka:** kiểm tra nhánh kết quả chưa chắc chắn; không tự publish vô hạn.
5. **Crash sau DB commit trước Kafka commit:** restart không đánh mất ý định phát event nếu có outbox.
6. **Crash sau Kafka publish trước đánh dấu outbox:** relay publish lại nhưng downstream không nhân đôi side effect.
7. **Consumer DB commit xong, offset commit lỗi:** cùng input được giao lại nhưng inbox unique constraint chặn ghi trùng.
8. **Nhiều instance và rebalance:** duplicate delivery không gây mất tiền, sai order state hoặc phát trùng event nghiệp vụ.
9. **Outbox relay outage dài:** backlog tăng có cảnh báo và phục hồi sau khi Kafka/ACL được sửa.
10. **Schema/serializer lỗi:** event bị cách ly đúng chỗ, không làm hỏng trạng thái DB, có kế hoạch replay.

Khi kiểm thử, cần đối chiếu **dữ liệu DB cuối cùng**, **số event ID duy nhất đã commit trên Kafka**, **committed offset của consumer**, **số lần side effect thực tế** và **trạng thái outbox/inbox**. Số lần listener hoặc method Java được gọi không đủ để chứng minh exactly-once theo nghĩa nghiệp vụ.

## 17. Quyết định kiến trúc nên dựa vào yêu cầu nào?

| Yêu cầu chính | Phương án thường phù hợp |
|---|---|
| DB là nguồn dữ liệu chính, không được mất event thay đổi trạng thái | Transactional outbox + relay/CDC + idempotent consumers |
| Consume Kafka, cập nhật DB và không nhân đôi side effect | Transactional inbox + DB unique constraint; offset commit at-least-once |
| Consume Kafka rồi produce Kafka, không có resource ngoài Kafka | Kafka transaction + offset trong cùng transaction, downstream `read_committed` |
| Nhiều hệ thống có nghiệp vụ dài, cần bù trừ | Saga/workflow + compensation + reconciliation |
| Chỉ cần đồng bộ best-effort, chấp nhận một số bất nhất nhỏ và có quy trình sửa | Transaction synchronization với monitoring và repair job rõ ràng |

Không có một annotation nào giải quyết đồng thời mọi trường hợp. Với hệ thống thanh toán, tồn kho hoặc dữ liệu quan trọng, nên ưu tiên kiến trúc **có thể phục hồi sau crash** và **đối soát được**, thay vì chỉ dựa vào đường thành công khi hai commit liên tiếp đều chạy trơn tru.

## 18. Nguyên tắc cốt lõi

1. Database và Kafka là hai resource có transaction boundary khác nhau; Spring transaction synchronization không tạo atomic commit xuyên hai hệ thống.
2. **Commit thứ nhất đã thành công thì transaction thứ hai lỗi không thể tự rollback thứ nhất.**
3. DB-first tạo nguy cơ **DB có dữ liệu nhưng event Kafka thiếu**; Kafka-first tạo nguy cơ **event Kafka có nhưng DB thiếu**.
4. Timeout ở bước commit có thể làm kết quả **không chắc chắn**; cần đối soát trước khi retry hoặc compensation.
5. Không đánh đồng `KafkaTemplate.send()` thành công với Kafka transaction commit đã hoàn tất.
6. Dùng stable request/event ID và idempotency để client, relay và consumer có thể thử lại an toàn.
7. Với DB→Kafka quan trọng, ưu tiên transactional outbox; với Kafka→DB, ưu tiên inbox trong cùng DB transaction với side effect.
8. Kafka transaction là công cụ mạnh cho Kafka→Kafka và transactional offset commit, nhưng không tự bao phủ database/HTTP.
9. DLT, reset offset và retry listener không thay thế repair/reconciliation của partial commit.
10. Kiểm thử fault window **giữa hai lần commit**, đo trạng thái thực tế của DB, Kafka, offset và downstream thay vì chỉ nhìn exception.

**Kết luận:** “Commit transaction thứ hai thất bại” là tình huống minh họa rõ nhất ranh giới của việc điều phối DB transaction và Kafka transaction bằng Spring. Khi transaction thứ nhất đã commit, không thể trả hệ thống về trạng thái cũ chỉ bằng rollback ở transaction thứ hai. Thiết kế đáng tin cậy cần chuẩn bị từ trước một chiến lược phục hồi: outbox/inbox, idempotency, provenance, reconciliation và compensation khi cần. Mục tiêu không phải giả định partial commit sẽ không bao giờ xảy ra, mà là bảo đảm hệ thống vẫn có thể phát hiện, sửa và đối soát chính xác sau khi nó xảy ra.
