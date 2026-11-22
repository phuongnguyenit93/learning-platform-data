# Phát event sau khi RPC thành công

## 1. Event phải phản ánh một sự thật đã được commit

Trong **SPRING_GRPC**, client gọi RPC theo hợp đồng Protocol Buffers; Spring service adapter chuyển request thành command và gọi application use case. Khi use case làm thay đổi trạng thái, hệ thống thường cần thông báo cho các service khác bằng message broker.

Ví dụ, sau khi tạo đơn hàng thành công, hệ thống có thể phát `OrderCreated` để inventory, notification hoặc analytics xử lý. Event này biểu đạt một sự thật đã xảy ra: đơn hàng đã được tạo. Nó khác với request `CreateOrder`, vốn chỉ biểu đạt yêu cầu cần thực hiện.

Điều kiện quan trọng là event chỉ được phát khi thay đổi nghiệp vụ đã commit. Nếu phát event trước khi transaction commit, consumer có thể nhìn thấy một sự kiện thành công dù database rollback. Nếu chỉ đợi method gRPC trả về rồi gửi message trực tiếp, process có thể crash ở giữa và làm mất event.

## 2. Xác định chính xác “RPC thành công” nghĩa là gì

Một RPC có thể đi qua nhiều mốc:

1. Request được xác thực và validation.
2. Use case thực hiện quy tắc nghiệp vụ.
3. Database transaction commit thay đổi trạng thái.
4. Event được ghi nhận bền vững để dispatch.
5. Broker xác nhận đã nhận event.
6. Consumer xử lý event.
7. Client nhận được response gRPC.

Các mốc này không đồng nghĩa. Với RPC đồng bộ tạo đơn, API có thể định nghĩa thành công khi bước 3 và 4 hoàn tất: dữ liệu đơn đã commit và event đã được ghi vào outbox trong cùng transaction. Relay có thể publish event sau đó.

Với RPC ingress chỉ nhận command bất đồng bộ, response `ACCEPTED` chỉ xác nhận command đã được ghi nhận theo durability contract. Không được phát `OrderCreated` ở thời điểm đó vì đơn hàng có thể chưa được tạo.

Nên mô tả rõ response của từng RPC là `COMPLETED` hay `ACCEPTED`. Event phải biểu đạt trạng thái nghiệp vụ thực tế, không được suy ra chỉ từ việc server đã gọi `observer.onCompleted()`.

## 3. Luồng phát event sau một RPC đồng bộ

Luồng đề xuất khi RPC thực hiện thay đổi trạng thái trong database:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as Spring gRPC adapter
    participant U as Application use case
    participant DB as Database
    participant O as Outbox relay
    participant B as Message broker
    participant W as Consumer
    C->>G: CreateOrder(request)
    G->>U: execute(CreateOrderCommand)
    U->>DB: Save order + outbox event
    DB-->>U: Commit
    U-->>G: OrderResult
    G-->>C: gRPC OK / response
    O->>DB: Read pending outbox
    O->>B: Publish OrderCreated
    B-->>O: Broker acknowledgement
    O->>DB: Mark published
    B->>W: Deliver event
    W->>W: Handle idempotently
~~~

Outbox record được commit cùng trạng thái đơn hàng. Vì vậy, dù relay chạy chậm hoặc tạm ngừng, event vẫn còn trong database để gửi lại. RPC không phải giữ connection mở cho đến khi mọi consumer hoàn tất.

Event có thể đến broker trước hoặc sau khi client nhận response, tùy lịch chạy relay và network. Hợp đồng cần dựa trên trạng thái commit, không dựa vào thứ tự quan sát giữa hai kênh giao tiếp.

## 4. Vì sao không publish trực tiếp sau khi gọi use case?

Một cách viết tưởng như đơn giản:

~~~java
OrderResult result = createOrderUseCase.execute(command);
kafkaTemplate.send("orders.events", result.orderId(), toEvent(result));
observer.onNext(toReply(result));
observer.onCompleted();
~~~

Cách này có khoảng trống lỗi giữa database và broker:

| Thời điểm lỗi | Hậu quả |
|---|---|
| Database commit, process crash trước `send` | Trạng thái đã đổi nhưng event bị mất |
| Broker nhận event, database transaction rollback | Consumer nhận event cho thay đổi chưa commit |
| Broker nhận event, acknowledgement bị mất | Producer có thể gửi lại, tạo duplicate |
| `send` trả future nhưng ứng dụng không theo dõi kết quả | RPC có thể báo thành công dù publish thất bại |

Chỉ đổi thứ tự thành publish trước database commit cũng không giải quyết được: broker có thể phát event trong khi transaction sau đó rollback. Database và broker thường không nằm trong cùng một transaction nguyên tử.

Với event quan trọng, dùng **transactional outbox** để lưu thay đổi nghiệp vụ và ý định phát event trong cùng database transaction. Publish trực tiếp chỉ phù hợp khi chấp nhận best-effort và có thể chấp nhận mất event.

## 5. Domain event và integration event

Hai loại event có mục đích khác nhau:

- **Domain event** mô tả điều đã xảy ra bên trong domain, ví dụ `OrderWasCreated`. Nó có thể mang kiểu dữ liệu nội bộ và phục vụ phối hợp use case.
- **Integration event** là hợp đồng công khai gửi sang hệ thống khác, ví dụ `orders.created.v1`. Nó cần schema ổn định, versioning và chỉ chứa dữ liệu được phép chia sẻ.

Không nhất thiết serialize trực tiếp domain event ra broker. Application/infrastructure layer có thể map domain event thành integration event để kiểm soát dữ liệu, tên event và khả năng tương thích.

Ví dụ:

~~~java
public record OrderCreatedDomainEvent(
        String orderId,
        String customerId,
        java.time.Instant createdAt) {}

public record OrderCreatedV1(
        String eventId,
        String orderId,
        String customerId,
        java.time.Instant occurredAt,
        String correlationId) {}
~~~

Domain event có thể không cần `eventId` hoặc `correlationId`; integration event cần những trường này để consumer deduplicate và truy vết.

## 6. Ghi business state và outbox trong cùng transaction

Use case nên sở hữu transaction bao trùm thay đổi nghiệp vụ và outbox record. Adapter gRPC chỉ gọi use case:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreateOrderService implements CreateOrderUseCase {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final OrderEventMapper eventMapper;
    private final IdGenerator ids;
    private final Clock clock;

    public CreateOrderService(
            OrderRepository orders,
            OutboxRepository outbox,
            OrderEventMapper eventMapper,
            IdGenerator ids,
            Clock clock) {
        this.orders = orders;
        this.outbox = outbox;
        this.eventMapper = eventMapper;
        this.ids = ids;
        this.clock = clock;
    }

    @Override
    @Transactional
    public OrderResult execute(CreateOrderCommand command) {
        Order order = Order.create(
                ids.newOrderId(),
                command.customerId(),
                command.lines(),
                clock.instant());

        orders.save(order);

        OrderCreatedV1 event = eventMapper.toIntegrationEvent(
                order,
                ids.newEventId(),
                command.correlationId());

        outbox.save(OutboxRecord.pending(
                event.eventId(),
                "orders.created",
                1,
                order.id(),
                event));

        return new OrderResult(order.id(), order.status());
    }
}
~~~

Đây là skeleton minh họa; repository và outbox serializer cần được triển khai theo persistence technology đang dùng. Điều quyết định là `orders.save(...)` và `outbox.save(...)` tham gia **cùng một transaction manager và cùng database transaction**. Nếu outbox nằm ở database khác hoặc dùng transaction manager khác, tính nguyên tử không còn được bảo đảm.

Khi transaction rollback, cả order và outbox record đều rollback. Khi commit, cả hai cùng tồn tại. Spring transaction proxy hoàn tất commit trước khi lời gọi qua proxy trả kết quả về adapter, miễn là use case được gọi qua bean proxy đúng cách.

## 7. Cấu trúc outbox record

Một outbox table thường có các trường:

| Field | Mục đích |
|---|---|
| `event_id` | ID duy nhất, dùng làm deduplication key |
| `event_type` | Tên integration event |
| `schema_version` | Phiên bản payload |
| `aggregate_id` | Entity/aggregate phát sinh event |
| `aggregate_version` | Thứ tự phiên bản của aggregate nếu cần |
| `payload` | Nội dung event đã serialize |
| `created_at` | Thời điểm ghi event |
| `published_at` | Thời điểm broker xác nhận |
| `status` / `attempts` | Trạng thái dispatch và số lần thử |
| `next_attempt_at` | Thời điểm retry tiếp theo nếu dùng backoff |

Đặt unique constraint cho `event_id`. Có thể thêm index cho các record chưa publish theo `status` và `created_at`/`next_attempt_at`. Cần chính sách lưu trữ hoặc dọn record đã publish để outbox không tăng vô hạn.

Không lưu credential hoặc toàn bộ gRPC metadata trong payload. Chỉ đưa thông tin nghiệp vụ và context đã được cho phép.

## 8. Relay publish event và chỉ đánh dấu sau acknowledgement

Outbox relay đọc record pending, gửi event đến broker rồi mới đánh dấu đã publish:

~~~java
public void publishOne(OutboxRecord record) {
    try {
        kafkaTemplate.send(
                topicFor(record.eventType()),
                record.aggregateId(),
                record.payload())
            .get(5, TimeUnit.SECONDS);

        outboxRepository.markPublished(
                record.eventId(),
                clock.instant());
    } catch (Exception ex) {
        outboxRepository.scheduleRetry(
                record.eventId(),
                nextAttempt(record.attempts()),
                safeErrorCode(ex));
    }
}
~~~

Ví dụ dùng `get` trong relay worker để minh họa việc chờ broker acknowledgement; không gọi đoạn blocking này trên gRPC event loop. Có thể dùng callback bất đồng bộ nếu relay được thiết kế theo mô hình đó.

Chỉ đánh dấu published sau acknowledgement. Nếu process crash sau broker acknowledgement nhưng trước khi cập nhật database, record vẫn pending và sẽ được publish lại. Đây là duplicate có chủ đích để tránh mất event; consumer phải idempotent.

Khi có nhiều relay instance, cần cơ chế claim/lease hoặc khóa hàng trong thời gian ngắn để tránh cùng lúc xử lý một record. Với PostgreSQL có thể dùng `FOR UPDATE SKIP LOCKED`; lựa chọn cụ thể phụ thuộc database. Không giữ transaction database mở trong suốt thời gian chờ network broker nếu có thể tránh được.

## 9. At-least-once và idempotent consumer

Transactional outbox bảo đảm event không bị mất giữa database commit và ý định publish, nhưng thường tạo delivery semantics **at-least-once**. Consumer có thể nhận cùng event nhiều lần.

Consumer cần:

1. Dùng `eventId` làm khóa nhận diện.
2. Ghi nhận event đã xử lý bằng unique constraint hoặc inbox table.
3. Thực hiện side effect và ghi inbox marker trong cùng transaction nếu cùng database.
4. Chỉ ack/commit offset sau khi xử lý đạt mốc an toàn.
5. Có retry/backoff và dead-letter flow cho lỗi không thể phục hồi.

Nếu consumer gọi một hệ thống ngoài database, idempotency key cần được truyền đến hệ thống đó hoặc dùng một cơ chế phối hợp khác. Chỉ lưu marker trước khi gọi side effect có thể làm mất công việc nếu process crash; lưu marker sau side effect có thể gây lặp nếu crash ở giữa. Cần chọn transaction boundary hoặc API idempotency phù hợp.

## 10. Spring @TransactionalEventListener có vai trò gì?

Spring có `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` để chạy listener sau khi transaction commit:

~~~java
@Component
public class OrderLocalEventListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedDomainEvent event) {
        localCache.evict(event.orderId());
    }
}
~~~

Đây là lựa chọn phù hợp cho phản ứng nội bộ best-effort như evict cache hoặc cập nhật một thành phần trong cùng process. Listener không chạy nếu transaction rollback.

Tuy nhiên, `AFTER_COMMIT` không phải durable message delivery. Nếu process crash sau database commit nhưng trước khi listener publish ra broker, event vẫn có thể mất. Nếu listener gửi broker và broker ack bị mất, có thể có duplicate. Vì vậy, với integration event quan trọng, hãy ghi outbox trong transaction thay vì chỉ dựa vào callback sau commit.

Không dùng `@TransactionalEventListener` để tạo cảm giác rằng database và broker đã được commit nguyên tử.

## 11. Adapter gRPC chỉ trả response từ kết quả use case

Adapter không nên tự quyết định event đã xảy ra chỉ vì nhận được một request hợp lệ. Nó gọi use case; use case commit state và outbox; adapter map kết quả thành protobuf response:

~~~java
@Override
public void createOrder(
        CreateOrderRequest request,
        StreamObserver<CreateOrderReply> observer) {
    try {
        CreateOrderCommand command = mapper.toCommand(
                request,
                callerContext.current());

        OrderResult result = createOrderUseCase.execute(command);

        observer.onNext(CreateOrderReply.newBuilder()
                .setOrderId(result.orderId())
                .setStatus(result.status())
                .build());
        observer.onCompleted();
    } catch (OrderValidationException ex) {
        observer.onError(Status.INVALID_ARGUMENT
                .withDescription("Invalid order request")
                .asRuntimeException());
    } catch (RuntimeException ex) {
        observer.onError(Status.INTERNAL
                .withDescription("Unable to create order")
                .asRuntimeException());
    }
}
~~~

Với cách tổ chức này, `execute(...)` trả về sau khi transaction proxy đã commit thành công. Nếu commit thất bại, adapter không nhận được kết quả thành công và không gửi response thành công. Outbox relay có thể publish event độc lập sau commit.

Không publish event trong `finally`, `onCompleted()` hoặc một callback chỉ phản ánh transport. `onCompleted()` có nghĩa server đã kết thúc response stream; nó không phải transaction commit hook và cũng không chứng minh client đã nhận response.

## 12. Deadline và cancellation không đảo ngược commit

Client có thể hủy RPC hoặc deadline hết ở thời điểm gần lúc transaction commit:

- Nếu transaction rollback trước commit, outbox record cũng không tồn tại.
- Nếu transaction đã commit, event đã được ghi nhận để dispatch; client cancel sau đó không tự rollback dữ liệu hoặc xóa outbox.
- Nếu response bị mất sau commit, client có thể retry và cần idempotency key để nhận lại cùng kết quả.

Không dùng cancellation của gRPC làm cơ chế hủy event đã commit. Nếu nghiệp vụ cần hoàn tác hoặc hủy một hành động đã hoàn tất, phát command bù như `CancelOrder` hoặc `RefundPayment`; đó là một hành động nghiệp vụ mới, không phải xóa event lịch sử.

## 13. Chọn event payload và thứ tự

Integration event nên chứa dữ liệu mà consumer cần, không nhất thiết sao chép toàn bộ aggregate:

~~~json
{
  "eventId": "evt-31a7",
  "eventType": "orders.created",
  "schemaVersion": 1,
  "aggregateId": "order-42",
  "aggregateVersion": 1,
  "correlationId": "req-7c20",
  "occurredAt": "2026-11-19T10:15:30Z",
  "payload": {
    "orderId": "order-42",
    "customerId": "customer-9",
    "status": "CREATED"
  }
}
~~~

Chọn broker key theo aggregate nếu consumer cần xử lý event của cùng entity theo thứ tự. Với Kafka, partition bảo đảm thứ tự trong partition; consumer vẫn phải tránh xử lý song song các record cùng aggregate theo cách làm đảo thứ tự side effect. `aggregateVersion` giúp consumer phát hiện event thiếu, trùng hoặc đến sai thứ tự.

Version schema event độc lập với version của RPC request. Thêm field theo quy tắc tương thích và không thay đổi ý nghĩa event đã phát hành. Một event `orders.created` phải luôn có nghĩa đơn hàng đã được tạo, không đổi thành “đã nhận yêu cầu tạo đơn”.

## 14. Khi nào cần chờ broker trước khi trả gRPC response?

Với outbox, cách thường dùng là trả response sau khi business transaction commit và outbox record đã được lưu bền vững. Broker relay có thể gửi sau đó. Điều này giảm latency và tránh giữ RPC mở trong lúc broker chậm.

Nếu hợp đồng bắt buộc response chỉ thành công khi broker đã xác nhận event, hệ thống có thể chờ publisher acknowledgement sau commit. Tuy vậy, cần nhận thức:

- Database đã commit trước khi chờ broker.
- Nếu broker không xác nhận, không thể tự động giả vờ database chưa thay đổi.
- Client retry phải dùng idempotency key.
- Có thể cần trả trạng thái “đã commit, đang chờ publish” qua operation status thay vì báo một lỗi chung khiến caller tưởng giao dịch chưa xảy ra.

Không có transaction nguyên tử giữa database và broker chỉ vì ứng dụng đợi `send().get()`. Outbox vẫn là cơ chế bền vững để retry và khôi phục sau lỗi.

## 15. Kiểm thử event sau RPC thành công

Kiểm thử cần xác minh quan hệ giữa commit, response và event:

| Kịch bản | Điều cần xác minh |
|---|---|
| Tạo đơn thành công | Order và outbox record cùng commit |
| Validation thất bại | Không có order và không có event |
| Transaction rollback | Outbox record không tồn tại |
| Broker tạm ngừng | Outbox vẫn pending và RPC theo đúng mốc success đã công bố |
| Relay publish thành công | Broker nhận đúng event type, ID, key và payload |
| Relay crash sau broker ack | Event có thể được gửi lại; consumer không lặp side effect |
| Listener `AFTER_COMMIT` | Không chạy khi transaction rollback |
| Process crash sau commit trước relay | Outbox record còn lại và được publish sau recovery |
| Client cancel sau commit | Business state/outbox không bị xóa |
| Client retry cùng idempotency key | Không tạo đơn hoặc event nghiệp vụ trùng |
| Event cùng aggregate | Ordering/version được giữ theo policy |
| Consumer lỗi vĩnh viễn | Retry giới hạn và dead-letter có thể quan sát |

Unit test use case nên kiểm tra repository và outbox cùng tham gia transaction. Integration test với database và broker thật/containerized mới xác minh commit, relay, acknowledgement và redelivery. Chỉ mock `KafkaTemplate` không chứng minh event được publish bền vững.

## 16. Quan sát và chẩn đoán

Theo dõi riêng các mốc:

- RPC success/failure theo method và gRPC status.
- Business transaction commit/rollback.
- Số outbox pending, tuổi record cũ nhất và retry count.
- Thời gian từ commit đến broker acknowledgement.
- Publish failure, broker timeout và duplicate publish.
- Consumer lag, duplicate hit, dead-letter và processing latency.
- Khoảng cách giữa `occurredAt`, `publishedAt` và thời điểm consumer xử lý.
- `eventId`, `aggregateId`, `aggregateVersion`, correlation/trace ID trong log và trace.

Không dùng event ID hoặc aggregate ID làm metric label có cardinality cao. Dùng chúng trong log/trace; metrics nên nhóm theo event type, topic, status và consumer.

Nếu client nhận gRPC OK nhưng event chưa đến consumer, kiểm tra outbox record, relay lag, broker acknowledgement, topic/partition và consumer lag. RPC OK theo hợp đồng outbox có thể chỉ khẳng định event đã được ghi bền vững để dispatch, không phải consumer đã xử lý.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Phát event trước database commit | Consumer thấy sự kiện cho transaction rollback | Ghi outbox trong transaction |
| Chỉ publish sau khi method gRPC trả về | Process crash có thể làm mất event | Ghi outbox trước khi transaction commit |
| Dùng `onCompleted()` làm commit hook | Trộn transport lifecycle với transaction lifecycle | Phát event từ outbox sau commit |
| Coi `AFTER_COMMIT` là durable | Crash sau commit có thể mất event | Dùng transactional outbox |
| Đánh dấu outbox published trước broker ack | Mất event khi broker từ chối | Mark published sau acknowledgement |
| Giả định outbox loại bỏ duplicate | Consumer có thể nhận lại event | Idempotent consumer theo event ID |
| Phát `OrderCreated` ngay khi command được accepted | Gửi thông tin nghiệp vụ sai | Phát event sau khi use case commit |
| Retry RPC tạo event ID mới | Một ý định có thể phát nhiều event | Idempotency key và event ID ổn định |
| Chờ mọi consumer hoàn tất trước khi trả RPC | RPC kéo dài và phụ thuộc toàn bộ downstream | Trả theo mốc commit/acceptance đã công bố |

**Ghi nhớ:** Event thành công phải biểu đạt thay đổi nghiệp vụ đã commit. Với Spring gRPC, use case nên ghi business state và outbox record trong cùng transaction; adapter trả response sau khi use case commit, còn relay publish event và đánh dấu sau broker acknowledgement. Delivery thường là at-least-once nên consumer phải idempotent. `AFTER_COMMIT` hữu ích cho phản ứng nội bộ best-effort, nhưng không thay thế outbox cho integration event quan trọng.
