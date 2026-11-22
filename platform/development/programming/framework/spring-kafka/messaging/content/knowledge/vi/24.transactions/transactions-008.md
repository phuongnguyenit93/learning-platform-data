# Gửi Kafka và cập nhật database

Một thao tác nghiệp vụ thường cần vừa cập nhật dữ liệu trong database vừa phát sự kiện lên Kafka. Ví dụ, khi tạo đơn hàng, ứng dụng lưu đơn hàng vào cơ sở dữ liệu và gửi sự kiện `OrderCreated` để các dịch vụ kho, thanh toán hoặc thông báo tiếp tục xử lý.

Hai thao tác này tác động lên hai hệ thống lưu trữ độc lập. Nếu database commit nhưng việc gửi Kafka thất bại, các dịch vụ khác không biết đơn hàng đã được tạo. Nếu Kafka nhận sự kiện nhưng transaction database rollback, consumer có thể xử lý một đơn hàng không tồn tại. Đây là bài toán *dual write*.

Để giải quyết, cần xác định rõ ranh giới transaction và cách bảo đảm sự kiện không bị mất khi tiến trình dừng giữa hai thao tác. Với ứng dụng Spring Kafka dùng database quan hệ, Transactional Outbox là một lựa chọn phổ biến: lưu thay đổi nghiệp vụ và ý định phát sự kiện trong cùng transaction database, sau đó một tiến trình relay chuyển sự kiện sang Kafka.

## 1. Vì sao hai lệnh ghi độc lập có thể lệch nhau?

Một cách triển khai dễ gặp là gọi repository và `KafkaTemplate` trong cùng một phương thức:

```java
@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Transactional
    public Order create(CreateOrder command) {
        Order order = Order.create(command);
        orderRepository.save(order);

        kafkaTemplate.send(
                "orders",
                order.getId().toString(),
                new OrderCreated(order.getId(), order.getCustomerId()));

        return order;
    }
}
```

Đoạn mã này chưa tạo ra một transaction nguyên tử bao trùm cả database lẫn Kafka. `@Transactional` thường điều khiển transaction của transaction manager đang áp dụng cho phương thức, ví dụ `JpaTransactionManager`. Lệnh `KafkaTemplate.send()` lại gửi dữ liệu qua producer Kafka và thường trả về kết quả bất đồng bộ.

Hai tình huống có thể xảy ra:

| Thứ tự sự cố | Kết quả |
| --- | --- |
| Database commit, sau đó publish Kafka thất bại | Đơn hàng tồn tại nhưng không có sự kiện để các dịch vụ khác xử lý |
| Kafka publish thành công, sau đó database rollback | Sự kiện đã phát nhưng dữ liệu nghiệp vụ không tồn tại |
| Publish trả về future nhưng phương thức không chờ kết quả | Database có thể commit trước khi ứng dụng biết publish thất bại |

Chờ kết quả `send()` bằng `get()` có thể giúp phát hiện lỗi publish trước khi phương thức kết thúc, nhưng không biến hai tài nguyên thành một transaction nguyên tử. Nếu Kafka đã nhận record rồi transaction database rollback, sự kiện vẫn tồn tại. Nếu database commit rồi tiến trình dừng trước khi gửi Kafka, sự kiện vẫn có thể bị mất.

Vì vậy, việc đặt hai lệnh trong cùng một phương thức Java hoặc cùng một annotation `@Transactional` không đủ để bảo đảm dual write nhất quán.

## 2. Transaction Kafka và transaction database có phạm vi khác nhau

Spring Kafka hỗ trợ transaction cho producer Kafka. Khi producer tham gia Kafka transaction, nhiều record được gửi trong transaction có thể được commit hoặc abort cùng nhau. Điều này hữu ích khi một luồng cần publish nhiều record Kafka như một đơn vị hoặc khi triển khai consume-transform-produce với semantics phù hợp.

Tuy nhiên, Kafka transaction không tự động bao gồm transaction của PostgreSQL, MySQL hay database quan hệ khác. `KafkaTransactionManager` quản lý tài nguyên Kafka; `JpaTransactionManager` hoặc `DataSourceTransactionManager` quản lý tài nguyên database. Chọn một transaction manager cho `@Transactional` không tự làm cho transaction manager còn lại trở thành một phần của cùng transaction nguyên tử.

Spring có cơ chế transaction synchronization để phối hợp thứ tự commit giữa một số transaction manager. Cách phối hợp này vẫn có thể gặp trạng thái một tài nguyên đã commit trong khi tài nguyên kia commit thất bại. Nếu cần atomic commit thực sự giữa nhiều resource, phải triển khai distributed transaction/XA với các resource manager hỗ trợ và chấp nhận chi phí, cấu hình cùng ràng buộc vận hành tương ứng. Đây không phải mặc định của `KafkaTemplate` và JPA.

Hãy phân biệt ba mục tiêu:

- **Kafka transaction:** bảo đảm nhóm thao tác ghi Kafka nằm trong một Kafka transaction.
- **Database transaction:** bảo đảm các thay đổi trong cùng database commit hoặc rollback cùng nhau.
- **Nhất quán giữa database và Kafka:** cần một cơ chế phối hợp rõ ràng, chẳng hạn Outbox, CDC hoặc distributed transaction được thiết kế đầy đủ.

## 3. Transactional Outbox giải quyết dual write

Transactional Outbox lưu sự kiện cần phát vào một bảng outbox trong cùng database với dữ liệu nghiệp vụ. Phương thức nghiệp vụ thực hiện hai thao tác trong một database transaction:

1. Ghi hoặc cập nhật dữ liệu nghiệp vụ, ví dụ đơn hàng.
2. Ghi một hàng outbox chứa event ID, loại sự kiện, khóa aggregate và payload cần gửi.

Nếu transaction commit, cả đơn hàng và hàng outbox đều tồn tại. Nếu transaction rollback, cả hai đều không tồn tại. Một tiến trình relay đọc các hàng outbox chưa phát và gửi chúng lên Kafka.

```text
                 Một database transaction
              +-------------------------------+
Command ----> | UPDATE/INSERT orders           |
              | INSERT outbox_event            |
              +---------------+---------------+
                              |
                         COMMIT / ROLLBACK
                              |
                 Relay đọc outbox đã commit
                              |
                              v
                       KafkaTemplate
                              |
                              v
                       Kafka topic
```

Outbox làm cho *ý định phát sự kiện* được lưu bền vững cùng thay đổi nghiệp vụ. Nếu ứng dụng dừng sau commit, hàng outbox vẫn còn để relay gửi khi hoạt động trở lại.

## 4. Thiết kế bảng outbox

Một bảng outbox cơ bản có thể gồm các trường:

```sql
CREATE TABLE outbox_event (
    id             VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(150) NOT NULL,
    event_version  INTEGER NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL,
    attempts       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (published_at, created_at);
```

Đây là schema minh họa; kiểu UUID, JSON/JSONB, timestamp và cú pháp index nên được điều chỉnh theo database đang dùng. Trong môi trường có nhiều relay instance, có thể bổ sung `status`, `locked_until`, `lease_owner`, `last_error` hoặc `next_attempt_at` để quản lý việc claim và retry.

Ý nghĩa các trường chính:

- `id`: event ID duy nhất, dùng để truy vết và chống xử lý trùng.
- `aggregate_type` và `aggregate_id`: xác định đối tượng nghiệp vụ phát sinh sự kiện.
- `event_type` và `event_version`: cho consumer biết loại và phiên bản schema.
- `payload`: nội dung sự kiện đã được serialize.
- `created_at`: thời điểm sự kiện được tạo trong transaction nghiệp vụ.
- `published_at`: thời điểm relay xác nhận Kafka đã nhận sự kiện.
- `attempts`: số lần relay đã thử publish.

Không nên lưu toàn bộ entity JPA một cách tùy tiện làm payload. Hãy định nghĩa event contract ổn định, chỉ chứa dữ liệu cần cho consumer và có chiến lược tiến hóa schema.

## 5. Ghi dữ liệu nghiệp vụ và outbox trong cùng transaction

Service nghiệp vụ không gửi Kafka trực tiếp. Nó lưu entity và một bản ghi outbox bằng cùng repository/database transaction:

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;

    OrderService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Order create(CreateOrder command) {
        Order order = Order.create(command);
        orderRepository.save(order);

        var event = new OrderCreated(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                Instant.now());

        outboxRepository.save(OutboxEvent.pending(
                event.eventId(),
                "Order",
                order.getId().toString(),
                "OrderCreated",
                1,
                writeJson(event)));

        return order;
    }

    private String writeJson(Object event) {
        try {
            return objectMapper.writeValueAsString(event);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize outbox event", ex);
        }
    }
}
```

`Order`, `OrderCreated`, `OutboxEvent`, repository và `ObjectMapper` là các thành phần minh họa của ứng dụng. Điều kiện quan trọng là hai repository cùng tham gia một transaction manager database và cùng một transaction. Không được đặt outbox ở một database độc lập rồi giả định nó tự commit cùng database đơn hàng.

Nếu serialize event thất bại, phương thức ném exception và transaction database rollback. Khi đó không có đơn hàng được commit mà thiếu outbox event tương ứng.

## 6. Relay đọc outbox và publish Kafka

Một relay dạng polling có thể chạy theo lịch, lấy các hàng chưa publish, gửi chúng bằng `KafkaTemplate`, rồi đánh dấu đã publish khi broker xác nhận thành công.

```java
import java.util.concurrent.TimeUnit;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class OutboxPublisher {

    private final OutboxRepository outboxRepository;
    private final OutboxStatusService statusService;
    private final KafkaTemplate<String, String> kafkaTemplate;

    OutboxPublisher(
            OutboxRepository outboxRepository,
            OutboxStatusService statusService,
            KafkaTemplate<String, String> kafkaTemplate) {
        this.outboxRepository = outboxRepository;
        this.statusService = statusService;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Scheduled(fixedDelayString = "${app.outbox.poll-delay:1000}")
    public void publishPending() {
        for (OutboxEvent event : outboxRepository.findPendingBatch(100)) {
            try {
                kafkaTemplate.send(
                        "domain-events",
                        event.getAggregateId(),
                        event.getPayload()).get(10, TimeUnit.SECONDS);

                statusService.markPublished(event.getId());
            }
            catch (Exception ex) {
                statusService.recordPublishFailure(event.getId(), ex);
            }
        }
    }
}
```

Ví dụ dùng `get()` để chờ kết quả gửi trước khi đánh dấu outbox row là published. `OutboxStatusService` cần cập nhật trạng thái bằng một database transaction riêng. Trong Spring Kafka hiện đại, `send()` trả về `CompletableFuture`; các phiên bản cũ hơn dùng kiểu future khác, nhưng đều có thể được chờ bằng API `Future.get()`.

Đây là skeleton để giải thích luồng, chưa phải bộ relay production hoàn chỉnh. Nếu nhiều instance cùng chạy, `findPendingBatch()` phải claim record an toàn để hai instance không đồng thời xử lý cùng một hàng. Có thể dùng row locking như `SELECT ... FOR UPDATE SKIP LOCKED`, trạng thái lease có thời hạn hoặc một cơ chế claim tương đương. Không giữ transaction/row lock database trong suốt thời gian gọi Kafka nếu thời gian mạng có thể kéo dài; thường nên claim trong transaction ngắn, commit claim, publish bên ngoài rồi cập nhật kết quả.

Khi publish thành công, đánh dấu `published_at` hoặc trạng thái `PUBLISHED`. Khi publish thất bại, giữ record ở trạng thái có thể thử lại, tăng `attempts`, lưu lỗi và đặt thời điểm thử tiếp theo theo backoff. Cần có chính sách cho lỗi vĩnh viễn để record không bị retry vô hạn mà không được chú ý.

## 7. Vì sao Outbox vẫn có thể gửi trùng?

Outbox bảo đảm thay đổi nghiệp vụ và ý định phát sự kiện được commit cùng nhau. Tuy nhiên, relay và Kafka vẫn là hai bước riêng. Có một cửa sổ lỗi:

1. Kafka đã xác nhận record được ghi thành công.
2. Relay dừng trước khi cập nhật `published_at` trong database.
3. Khi khởi động lại, relay thấy hàng outbox vẫn chưa publish và gửi lại record.

Vì vậy, Outbox polling thường cung cấp semantics *at-least-once*: sự kiện không bị mất do relay dừng trước lần publish đầu tiên, nhưng có thể được gửi nhiều lần. Không nên mô tả nó là exactly-once end-to-end.

Thiết kế consumer idempotent để việc nhận cùng event nhiều lần không tạo side effect lặp. Một cách phổ biến là bảng `processed_event` có khóa duy nhất theo event ID. Trong cùng database transaction với thay đổi nghiệp vụ, consumer ghi event ID; nếu ID đã tồn tại thì bỏ qua sự kiện trùng.

```java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    inventoryService.reserve(event.orderId());
}
```

`insertIfAbsent` là thao tác repository minh họa; cần triển khai bằng unique constraint và câu lệnh phù hợp với database. Việc ghi dấu đã xử lý và cập nhật nghiệp vụ phải nằm trong cùng transaction. Nếu chỉ ghi dấu trước rồi cập nhật nghiệp vụ ở transaction khác, lỗi giữa hai bước có thể làm sự kiện bị bỏ qua ở lần nhận sau.

## 8. Giữ thứ tự sự kiện theo aggregate

Nếu nhiều sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự, relay nên publish với Kafka key là `aggregate_id`. Kafka đưa cùng key vào cùng partition theo partitioner thông thường, từ đó bảo toàn thứ tự ghi trong partition.

Tuy nhiên, key không tự giải quyết thứ tự nếu nhiều relay instance claim và publish các event của cùng aggregate đồng thời. Có thể dùng `aggregate_version` hoặc `sequence_number`, chỉ cho phép publish event kế tiếp sau khi event trước đã được xác nhận, hoặc phân chia công việc relay theo aggregate/partition. Consumer cũng nên kiểm tra version để phát hiện sự kiện đến sai thứ tự.

Thứ tự giữa các aggregate khác nhau thường không cần được bảo đảm toàn cục. Tránh thiết kế một khóa Kafka duy nhất cho mọi sự kiện chỉ để tạo thứ tự toàn cục, vì điều đó có thể dồn toàn bộ tải vào một partition.

## 9. Outbox polling và CDC

Có hai cách phổ biến để chuyển outbox sang Kafka:

| Cách | Hoạt động | Ưu điểm | Điều cần quản lý |
| --- | --- | --- | --- |
| Polling relay | Ứng dụng truy vấn hàng pending theo batch rồi gửi bằng `KafkaTemplate` | Dễ bắt đầu, dễ tùy biến nghiệp vụ và retry | Claim row, concurrency, backoff, dọn dữ liệu đã publish và duplicate |
| Change Data Capture (CDC) | Công cụ như Debezium đọc transaction log của database và phát thay đổi outbox sang Kafka | Không cần ứng dụng polling liên tục; đọc các thay đổi đã commit từ log | Connector, quyền đọc log, schema, offset connector, retention và vận hành hạ tầng CDC |

Với CDC, ứng dụng vẫn ghi dữ liệu nghiệp vụ và outbox trong cùng database transaction. Connector chỉ quan sát thay đổi đã commit trong transaction log và route hàng outbox thành Kafka record, thường qua Outbox Event Router của Debezium. CDC giảm phần code relay do ứng dụng sở hữu, nhưng vẫn cần thiết kế consumer idempotent vì quá trình giao nhận có thể lặp khi connector khôi phục từ offset.

Chọn polling khi muốn giữ cơ chế đơn giản trong ứng dụng và tải outbox vừa phải. Chọn CDC khi hệ thống đã có nền tảng vận hành CDC hoặc cần thông lượng lớn, độ trễ thấp và tách việc publish khỏi vòng đời ứng dụng.

## 10. Vì sao AFTER_COMMIT event listener chưa thay thế Outbox?

Một cách khác là phát Spring application event trong transaction rồi dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` để gửi Kafka sau khi database commit:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    kafkaTemplate.send("orders", event.orderId().toString(), event);
}
```

Cách này giúp không gửi sự kiện trước khi transaction database commit. Tuy nhiên, có một khoảng trống: database đã commit nhưng tiến trình dừng trước khi callback được thực thi hoặc trước khi publish Kafka thành công. Application event trong bộ nhớ không phải một hàng đợi bền vững. Nếu sự kiện bắt buộc không được mất, hãy ghi outbox trong transaction database thay vì chỉ dựa vào callback sau commit.

`AFTER_COMMIT` vẫn hữu ích cho tác vụ phụ có thể chấp nhận mất hoặc có cơ chế khôi phục riêng, chẳng hạn xóa cache hoặc gửi thông báo không quan trọng. Cần đánh giá rõ yêu cầu durability trước khi dùng.

## 11. Khi nào dùng Kafka transaction?

Kafka transaction phù hợp khi tính nguyên tử cần nằm trong Kafka, ví dụ producer ghi nhiều topic hoặc consumer đọc một record rồi ghi kết quả sang topic khác và commit offset trong cùng Kafka transaction. Cấu hình producer transaction ID và `KafkaTransactionManager` cho phép Spring Kafka quản lý transaction producer; consumer đọc dữ liệu transactional nên dùng `isolation.level=read_committed` khi cần chỉ thấy dữ liệu đã commit.

Nếu cùng một nghiệp vụ phải cập nhật database quan hệ và gửi Kafka, Kafka transaction một mình không giải quyết được dual write. Có thể dùng Outbox để database transaction lưu trạng thái cùng sự kiện; relay sau đó gửi event bằng Kafka producer. Nếu relay cần publish nhiều record Kafka như một nhóm nguyên tử, có thể bổ sung Kafka transaction cho nhóm publish, nhưng việc đánh dấu outbox trong database vẫn là một ranh giới khác và duplicate vẫn cần được xử lý.

## 12. Kiểm thử và vận hành Outbox

Kiểm thử cần bao gồm cả đường thành công và các điểm dừng giữa hai hệ thống:

1. Tạo đơn hàng thành công; xác minh hàng `orders` và `outbox_event` cùng commit.
2. Làm serialize event hoặc ghi outbox thất bại; xác minh transaction database rollback và đơn hàng không được commit.
3. Tắt Kafka trong lúc relay chạy; xác minh outbox row vẫn pending và được gửi sau khi Kafka hoạt động lại.
4. Mô phỏng relay dừng sau khi Kafka xác nhận nhưng trước khi đánh dấu published; xác minh duplicate có thể xuất hiện và consumer idempotent xử lý an toàn.
5. Chạy nhiều relay instance; xác minh cơ chế claim không làm mất record hoặc publish song song sai thứ tự trong cùng aggregate.
6. Gửi nhiều event cùng aggregate; xác minh Kafka key và sequence/version giữ đúng thứ tự yêu cầu.
7. Kiểm tra retry, DLT và cảnh báo khi một outbox row tồn tại quá lâu mà chưa publish.

Các chỉ số nên theo dõi gồm số hàng pending, tuổi của hàng pending cũ nhất, tốc độ publish, số lần publish lỗi, số hàng ở trạng thái lease quá hạn, thời gian từ `created_at` đến `published_at` và số duplicate bị consumer loại bỏ. Cần có chính sách retention/dọn dẹp outbox đã publish, nhưng chỉ xóa sau khoảng lưu đủ cho việc điều tra và replay.

## 13. Checklist lựa chọn giải pháp

- [ ] Đã xác định database transaction và Kafka transaction bảo vệ những tài nguyên nào.
- [ ] Không giả định một `@Transactional` mặc định làm database và Kafka commit nguyên tử.
- [ ] Nếu sự kiện bắt buộc không được mất, dữ liệu nghiệp vụ và outbox row được ghi trong cùng database transaction.
- [ ] Relay chỉ đánh dấu published sau khi Kafka xác nhận gửi thành công.
- [ ] Relay có cơ chế claim an toàn khi chạy nhiều instance và có backoff khi publish thất bại.
- [ ] Consumer có idempotency key và lưu dấu đã xử lý cùng transaction nghiệp vụ.
- [ ] Kafka key/aggregate sequence được thiết kế nếu cần ordering.
- [ ] Có monitoring cho outbox backlog, tuổi event, publish failure và duplicate.
- [ ] Có kiểm thử lỗi ở các khoảng giữa commit database, publish Kafka và cập nhật trạng thái outbox.

Khi database và Kafka không tham gia cùng một distributed transaction, Transactional Outbox là cách thực tế để tránh mất ý định phát sự kiện. Database commit trạng thái nghiệp vụ và outbox cùng nhau; relay gửi sự kiện theo kiểu at-least-once; consumer idempotent xử lý các lần giao lặp. Ba phần này phối hợp để tạo luồng messaging tin cậy mà không giả định hai hệ thống có chung một transaction cục bộ.
