# Luồng từ producer đến consumer

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events là cơ chế để một module công bố sự thật nghiệp vụ và các module khác phản ứng mà không cần gọi trực tiếp implementation nội bộ của nhau. Để thiết kế, triển khai và vận hành đúng, cần hiểu toàn bộ đường đi của event: từ lúc producer thay đổi trạng thái domain, tạo và publish event, qua transaction và Event Publication Registry, đến listener nội bộ hoặc adapter externalization, broker và consumer bên ngoài.

Một event có thể chỉ được xử lý trong cùng Spring application, hoặc được chuyển thành message để hệ thống khác nhận. Hai đường đi có chung ý tưởng về event contract nhưng có ranh giới giao nhận, transaction, retry và acknowledgement khác nhau. Bài này mô tả từng chặng, trách nhiệm của producer/consumer và các điểm cần kiểm soát để giao sự kiện đáng tin cậy.

## 1. Bức tranh tổng thể

Luồng cơ bản gồm các vai trò:

- **Producer:** module sở hữu domain transition và phát event mô tả sự thật đã xảy ra.
- **Application event mechanism:** nhận event và phân phối đến các listener được đăng ký trong ứng dụng.
- **Event Publication Registry:** theo dõi publication đến từng listener để biết listener nào đã hoàn tất hoặc còn chưa hoàn tất.
- **Listener:** module consumer trong cùng ứng dụng xử lý event theo trách nhiệm của mình.
- **Externalization adapter:** chuyển event nội bộ thành message theo contract vận chuyển khi cần giao cho hệ thống khác.
- **Broker:** lưu/chuyển message theo semantics của transport.
- **External consumer:** nhận message, xác minh contract và cập nhật dữ liệu hoặc thực hiện tác dụng phụ thuộc quyền sở hữu của nó.

~~~mermaid
flowchart LR
    A[Domain command] --> B[Producer module]
    B --> C[Domain state transition]
    C --> D[Publish application event]
    D --> E[Application event mechanism]
    E --> F[Event Publication Registry]
    E --> G[Internal listener A]
    E --> H[Internal listener B]
    E --> I[Externalization adapter]
    G --> J[Consumer module A]
    H --> K[Consumer module B]
    I --> L[Message broker]
    L --> M[External consumer]
~~~

Sơ đồ thể hiện các thành phần khái niệm. Thứ tự chính xác giữa việc ghi publication, gọi listener và externalization phụ thuộc cấu hình, transaction manager và adapter đang dùng. Không suy ra rằng mọi chặng đều nằm trong một transaction duy nhất.

## 2. Producer sở hữu sự thật nghiệp vụ

Producer là module có thẩm quyền đối với domain state tạo ra event. Ví dụ Orders sở hữu đơn hàng. Khi đơn hàng chuyển từ PAID sang CONFIRMED, Orders quyết định transition có hợp lệ không và công bố `OrderConfirmed`.

Producer chịu trách nhiệm:

- Xác thực command và domain invariant.
- Thực hiện thay đổi trạng thái trong transaction phù hợp.
- Tạo event mang ý nghĩa nghiệp vụ đã xảy ra.
- Cung cấp định danh và dữ liệu contract cần thiết cho consumer.
- Publish event tại điểm được thiết kế trong application flow.
- Bảo đảm ý định phát event gắn với thay đổi domain theo yêu cầu độ tin cậy.

Producer không nên phát event chỉ vì một method được gọi. Event phải phản ánh sự thật đã được domain chấp nhận. Nếu đơn hàng chưa commit hoặc transaction có thể rollback, tài liệu phải mô tả rõ listener nào chỉ được phép chạy sau commit.

Ví dụ domain transition:

~~~java
public OrderConfirmed confirm(Instant now) {
    if (status != OrderStatus.PAID) {
        throw new IllegalStateException("Only paid orders can be confirmed");
    }

    status = OrderStatus.CONFIRMED;
    version++;

    return new OrderConfirmed(
        UUID.randomUUID(),
        id,
        version,
        now,
        items
    );
}
~~~

Ví dụ này minh họa việc tạo event từ domain transition. Cách publish có thể đặt trong application service sau khi aggregate tạo event, hoặc dùng cơ chế domain event phù hợp với kiến trúc. Điều quan trọng là producer vẫn kiểm soát tính hợp lệ của transition và event không chứa implementation detail của repository hoặc entity ORM.

## 3. Event contract là giao diện giữa producer và consumer

Event contract định nghĩa điều consumer có thể dựa vào. Một contract tốt mô tả tên, ý nghĩa, payload, version và semantics giao nhận.

Ví dụ:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    long aggregateVersion,
    Instant occurredAt,
    List<OrderItem> items
) {}
~~~

Các trường có mục đích riêng:

| Trường | Mục đích |
|---|---|
| eventId | Nhận diện một lần công bố event |
| orderId | Xác định aggregate nghiệp vụ |
| aggregateVersion | Phát hiện event cũ hoặc sai thứ tự |
| occurredAt | Thời điểm nghiệp vụ xảy ra |
| items | Dữ liệu consumer cần để thực hiện trách nhiệm của mình |

Không đưa toàn bộ aggregate hoặc entity ORM vào event. Nếu consumer chỉ cần order ID và danh sách mặt hàng, payload nên chứa đúng thông tin đó theo contract đã thống nhất. Event có thể được serialize, lưu hoặc replay sau khi class nội bộ của producer đã thay đổi.

Tên event nên mô tả sự thật đã xảy ra, thường ở dạng quá khứ như `OrderConfirmed`, `PaymentAuthorized` hoặc `InventoryReserved`. Tên như `ProcessOrder` hoặc `UpdateInventory` giống command hơn là event.

## 4. Producer publish event trong application

Trong Spring, producer thường dùng `ApplicationEventPublisher` để công bố event:

~~~java
@Service
class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();

        OrderConfirmed event = order.confirm(Instant.now());

        orders.save(order);
        events.publishEvent(event);
    }
}
~~~

Lời gọi `publishEvent` chuyển event vào application event mechanism. Với transaction đang hoạt động, event có thể được publish trước khi transaction kết thúc. Vì vậy, publish event không đồng nghĩa transaction đã commit.

Nếu listener cần đọc trạng thái đã commit, dùng transactional event listener ở phase phù hợp hoặc `@ApplicationModuleListener` theo thiết kế. Nếu event cần được externalize bền vững, cần đánh giá transaction và cơ chế outbox/registry để không tạo khoảng trống giữa commit domain và gửi message.

## 5. Transaction boundary và thời điểm listener chạy

Có ba ý cần tách biệt:

1. Producer gọi `publishEvent`.
2. Transaction chứa thay đổi domain commit hoặc rollback.
3. Listener bắt đầu và hoàn tất xử lý.

Với listener đồng bộ thông thường, listener có thể được gọi trong thread của publisher khi event được phát. Với `@TransactionalEventListener`, listener được gắn vào transaction phase. Phase mặc định là AFTER_COMMIT; khi transaction commit thành công, callback mới được gọi.

~~~java
@Component
class OrderAuditListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        // The order transaction has committed.
        audit.record(event.orderId(), event.eventId());
    }
}
~~~

Các phase gồm BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION. Chọn phase theo semantics nghiệp vụ. Nếu không có transaction, transactional listener thường không được gọi trừ khi bật fallback execution có chủ đích.

Với listener sau commit, lỗi listener không thể rollback transaction nghiệp vụ đã commit. Nếu listener cần ghi database, cần transaction riêng thích hợp. Không coi một exception sau commit là bằng chứng producer transaction chưa thành công.

## 6. @ApplicationModuleListener và xử lý trong module consumer

Spring Modulith cung cấp `@ApplicationModuleListener` để diễn đạt listener module thường được xử lý bất đồng bộ sau commit và trong transaction riêng theo semantics của annotation ở phiên bản tương ứng.

~~~java
@Component
class InventoryEventListener {

    private final InventoryService inventory;

    InventoryEventListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        inventory.reserve(event.orderId(), event.items());
    }
}
~~~

Consumer Inventory chỉ chịu trách nhiệm giữ hàng. Nó không cần gọi repository nội bộ của Orders hoặc biết Notification/Shipping đang có listener nào. Event contract là điểm kết nối giữa các module.

Bất đồng bộ không có nghĩa listener bắt đầu ngay sau commit. Task có thể chờ executor queue, thread, database connection hoặc dependency ngoài. Tài liệu cần phân biệt thời điểm được lên lịch, thời điểm listener bắt đầu và thời điểm hoàn tất.

## 7. Event Publication Registry theo dõi điều gì?

Spring Modulith Event Publication Registry theo dõi việc giao application event đến từng listener trong ứng dụng. Khi event được publish, registry ghi nhận publication cho các listener phù hợp. Khi listener hoàn tất thành công, publication tương ứng được đánh dấu hoàn tất.

Một event có ba listener có thể tạo ba publication độc lập:

| Listener | Trạng thái ví dụ |
|---|---|
| InventoryListener | COMPLETED |
| NotificationListener | INCOMPLETE |
| AnalyticsListener | COMPLETED |

Trạng thái trên cho biết Inventory và Analytics đã hoàn tất publication của mình; Notification còn chưa hoàn tất. Nó không có nghĩa toàn bộ business workflow đã hoàn tất, cũng không phản ánh consumer ngoài broker.

Registry hữu ích để:
- Biết listener nào còn publication chưa hoàn tất.
- Phục hồi publication sau lỗi hoặc restart khi dùng cấu hình persistence phù hợp.
- Theo dõi delivery nội bộ theo từng listener.
- Phát hiện backlog và publication cũ.
- Hỗ trợ vận hành resubmit qua API được phiên bản Spring Modulith hỗ trợ.

Registry không thay thế event store dài hạn, broker, outbox hoặc process manager. Không truy cập trực tiếp schema nội bộ nếu framework cung cấp API phù hợp.

## 8. Listener thành công, thất bại và publication chưa hoàn tất

Một publication chỉ nên được xem là hoàn tất khi listener đã thực hiện xong trách nhiệm theo contract. Nếu listener ném exception, tiến trình dừng hoặc không ghi nhận được trạng thái hoàn tất, publication có thể còn ở trạng thái chưa hoàn tất.

Cần phân biệt:

- Listener chưa được thực thi.
- Listener đang chờ executor.
- Listener đang xử lý.
- Listener thất bại.
- Listener đã thực hiện side effect nhưng process dừng trước khi ghi nhận completion.
- Publication đã hoàn tất.

Đặc biệt, trường hợp side effect đã xảy ra nhưng completion chưa được ghi nhận có thể dẫn đến listener được gọi lại. Đây là lý do consumer cần idempotency. Không giả định publication chưa hoàn tất đồng nghĩa chắc chắn side effect chưa xảy ra.

Nếu cần phục hồi sau restart, cấu hình registry persistent và quy trình resubmit có kiểm soát. Resubmit không phải một thao tác vô hại: listener có thể được gọi lại và tạo side effect nếu không có bảo vệ duplicate.

## 9. Consumer nội bộ thực hiện trách nhiệm của module mình

Một consumer nội bộ là listener trong cùng Spring application. Consumer nhận event và cập nhật dữ liệu thuộc module sở hữu.

Ví dụ:

- Inventory nhận OrderConfirmed và tạo reservation.
- Notification nhận OrderConfirmed và tạo yêu cầu gửi thông báo.
- Analytics nhận OrderConfirmed và cập nhật projection.

Mỗi consumer nên:
- Chỉ phụ thuộc vào event contract được công bố.
- Thực hiện domain logic trong module của mình.
- Có transaction phù hợp với dữ liệu sở hữu.
- Chống xử lý trùng.
- Ghi log/metric có định danh để truy vết.
- Phát event kết quả nếu có sự thật nghiệp vụ mới.
- Không điều phối toàn bộ workflow nếu trách nhiệm đó thuộc process manager.

Một event có thể được nhiều consumer xử lý độc lập. Producer không cần biết số lượng hoặc trạng thái từng consumer trừ khi nghiệp vụ yêu cầu workflow đồng bộ có điều phối.

## 10. Từ application event đến broker message

Khi hệ thống khác cần nhận event, ứng dụng có thể externalize event qua adapter của Spring Modulith hoặc cơ chế tích hợp tương ứng. Adapter chuyển event nội bộ thành message theo destination và contract được cấu hình.

~~~mermaid
sequenceDiagram
    participant P as Producer module
    participant DB as Application database
    participant R as Publication Registry
    participant L as Internal listener
    participant A as Externalization adapter
    participant B as Broker
    participant C as External consumer

    P->>DB: Update domain in transaction
    P->>R: Publish application event
    Note over P,DB: Transaction boundary must be explicit
    R->>L: Deliver to internal listener
    L->>L: Process module responsibility
    L->>R: Mark publication complete
    R->>A: Externalize event
    A->>B: Publish serialized message
    B-->>A: Confirm/ack according to transport
    B->>C: Deliver message
    C->>C: Validate and process contract
~~~

Sơ đồ là góc nhìn khái niệm. Thứ tự cụ thể giữa registry, listener và adapter phụ thuộc integration và transaction configuration. Không giả định việc gửi broker nằm trong cùng transaction với database nếu chưa có cơ chế bảo đảm điều đó.

Adapter cần xác định:
- Event type nào được externalize.
- Destination/queue/topic tương ứng.
- Payload schema và version.
- Header metadata như event ID, correlation ID.
- Serializer và content type.
- Delivery/confirmation semantics.
- Retry và dead-letter behavior.

## 11. Broker đảm nhiệm vận chuyển message

Broker nhận message từ publisher/adapter và chuyển đến consumer theo semantics của công nghệ đang dùng. RabbitMQ thường tổ chức qua exchange, routing key và queue; Kafka tổ chức theo topic, partition và consumer group.

| Thành phần | Vai trò |
|---|---|
| Exchange/topic | Điểm định tuyến hoặc lưu luồng message |
| Queue/partition | Nơi message được giữ và phân phối |
| Routing key/key | Chọn đích hoặc partition |
| Consumer group | Phân chia việc đọc giữa các consumer instance |
| Acknowledgement/offset | Xác nhận tiến độ xử lý theo transport |
| Retry/DLQ | Giữ và chuyển message lỗi theo policy |

Broker không hiểu toàn bộ semantics domain. Nó vận chuyển bytes và metadata. Consumer vẫn phải xác thực schema, version, event type và quyền xử lý.

Broker acceptance cũng không đồng nghĩa consumer đã xử lý xong. Cần tách publisher confirmation, message delivery, consumer acknowledgement và business effect completion.

## 12. External consumer xử lý message

Consumer bên ngoài thường thực hiện các bước:

1. Nhận message và metadata.
2. Xác minh event type, schema version và content type.
3. Deserialize payload.
4. Kiểm tra event ID, correlation ID và business key.
5. Kiểm tra duplicate hoặc sequence.
6. Áp dụng domain logic trong transaction của consumer.
7. Ghi inbox/idempotency state cùng thay đổi domain.
8. Acknowledge message theo semantics transport sau khi commit phù hợp.

Ví dụ pseudo-code:

~~~java
@Transactional
public void handle(OrderConfirmed event) {
    if (inbox.exists(CONSUMER_NAME, event.eventId())) {
        return;
    }

    inbox.claim(CONSUMER_NAME, event.eventId());
    inventory.reserve(event.orderId(), event.items());
}
~~~

Trong triển khai thật, `exists` và `claim` cần được bảo vệ concurrency bằng unique constraint hoặc thao tác nguyên tử. Không dùng kiểm tra rồi ghi tách rời nếu hai consumer có thể xử lý đồng thời cùng event.

Nếu cập nhật domain và inbox nằm trong cùng transaction, duplicate delivery sau commit có thể được nhận diện mà không lặp tác dụng phụ. Acknowledgement phải được phối hợp với transaction để tránh mất message khi process dừng ở giữa.

## 13. Idempotency và at-least-once delivery

Trong hệ thống phân tán, message có thể được giao lại. Một consumer có thể xử lý thành công rồi mất kết nối trước khi broker nhận acknowledgement; broker sẽ giao message lại.

Vì vậy, hãy thiết kế consumer theo hướng idempotent:
- Dùng event ID ổn định để deduplicate một event.
- Dùng business operation ID nếu nhiều event/message có thể đại diện cho cùng một thao tác.
- Ghi inbox và domain update trong một transaction.
- Dùng unique constraint để xử lý cạnh tranh.
- Gửi cùng idempotency key khi gọi external API.
- Thiết kế state transition để lần xử lý lặp trở thành no-op hợp lệ.

Không tuyên bố exactly-once chỉ vì broker có acknowledgement hoặc registry có publication record. End-to-end exactly-once thường không thể suy ra từ một cơ chế đơn lẻ. Thiết kế thực tế thường kết hợp at-least-once delivery với idempotent processing.

## 14. Ordering và event đến muộn

Event được publish trước không nhất thiết được xử lý trước. Async listener, retry, nhiều partition hoặc nhiều consumer instance có thể làm thay đổi thứ tự quan sát.

Nếu thứ tự quan trọng:
- Gắn aggregate version hoặc sequence vào event.
- Chọn partition key theo aggregate ID khi transport hỗ trợ.
- Kiểm tra sequence trước khi cập nhật projection.
- Xử lý duplicate và event đến muộn.
- Xác định cách giữ event khi phát hiện thiếu sequence.
- Không dùng timestamp wall-clock làm thứ tự tuyệt đối giữa nhiều máy.

Ordering thường chỉ được bảo đảm trong một phạm vi cụ thể, chẳng hạn một queue hoặc một Kafka partition. Tài liệu contract phải ghi rõ phạm vi đó.

## 15. Retry, backoff và dead-letter

Retry giúp phục hồi lỗi tạm thời như network timeout, database deadlock hoặc downstream 503. Một policy nên xác định:

- Lỗi nào retryable.
- Timeout cho từng attempt.
- Số lần thử tối đa hoặc deadline tổng.
- Exponential backoff và jitter.
- Retry-After nếu downstream cung cấp.
- Retry owner ở listener, client, registry hay broker.
- Nơi giữ message khi hết budget.
- Ai được phép resubmit/replay.

Không retry lỗi dữ liệu hoặc business rejection một cách mù quáng. Khi retry budget hết, chuyển sang DLQ/quarantine, ghi nguyên nhân và giữ khả năng phục hồi sau khi sửa lỗi.

Với Spring Modulith, publication nội bộ chưa hoàn tất và message broker ở DLQ là hai boundary khác nhau. Registry theo dõi listener nội bộ; broker/consumer container quản lý delivery bên ngoài. Runbook cần chỉ rõ công cụ và owner cho từng loại.

## 16. Outbox và khoảng trống giữa database với broker

Nếu producer cập nhật database rồi gửi broker bằng hai thao tác độc lập, có thể xảy ra dual-write failure:

- Database commit thành công nhưng process dừng trước khi publish.
- Broker nhận message nhưng producer không ghi nhận được confirmation và gửi lại.
- Event bị mất hoặc bị duplicate nếu không có cơ chế phục hồi.

Transactional outbox ghi domain change và ý định gửi message vào cùng transaction. Relay đọc outbox và publish message sau commit. Nếu relay không chắc message đã được broker nhận, nó có thể gửi lại; consumer vẫn cần idempotency.

~~~mermaid
flowchart TD
    A[Producer transaction] --> B[Update domain state]
    B --> C[Insert outbox record]
    C --> D[Commit]
    D --> E[Outbox relay]
    E --> F[Broker publish]
    F --> G[Consumer]
    E --> H[Retry relay if outcome uncertain]
    H --> E
~~~

Outbox bảo vệ ý định publish ở phía producer. Nó không tự bảo đảm consumer xử lý đúng một lần. Kết hợp outbox với inbox/idempotency ở consumer khi cần độ tin cậy end-to-end.

Event Publication Registry và outbox có mục đích khác nhau. Registry theo dõi publication đến listener trong ứng dụng; outbox lưu ý định gửi message ra hệ thống khác. Chọn cơ chế theo boundary cần bảo vệ, không xem chúng là hai tên gọi cho cùng một thành phần.

## 17. Quan sát luồng từ đầu đến cuối

Muốn điều tra một event, cần nối được producer, listener, broker và consumer bằng metadata thống nhất.

Nên có:
- eventId: định danh event.
- correlationId: liên kết các message trong cùng business flow.
- causationId: message trực tiếp tạo ra event hiện tại.
- aggregateId và aggregateVersion: nhận diện đối tượng và thứ tự nghiệp vụ.
- eventType và schemaVersion: phân loại contract.
- producerName, listener/consumerName và destination: xác định chặng xử lý.

Metrics hữu ích:
- Event published/consumed rate.
- Listener duration và error rate.
- Incomplete publication count và oldest age.
- Executor queue depth.
- Outbox pending count/oldest age.
- Broker queue depth hoặc consumer lag.
- Retry rate, DLQ count và duplicate rate.
- End-to-end processing latency nếu đo được.

Dùng ID có cardinality cao trong logs/traces, không đưa chúng vào metric labels. Không ghi toàn bộ payload hoặc dữ liệu nhạy cảm chỉ để truy vết.

## 18. Kiểm thử luồng producer đến consumer

Không có một loại test nào chứng minh toàn bộ pipeline. Chia test theo boundary:

| Test | Xác minh |
|---|---|
| Producer unit test | Domain transition tạo đúng event |
| Application event test | Event được publish và listener nhận đúng |
| Transaction test | AFTER_COMMIT/rollback semantics |
| Module test | Module chỉ dùng API/event contract được phép |
| Registry test | Publication được ghi nhận và phục hồi theo cấu hình |
| Serialization/contract test | Payload tương thích schema |
| Broker integration test | Routing, confirm, ack, retry và DLQ |
| Consumer integration test | Inbox, idempotency và domain update |
| End-to-end scenario | Luồng nghiệp vụ đạt kết quả mong đợi qua các chặng |

Với listener bất đồng bộ, dùng điều kiện chờ có timeout thay cho `Thread.sleep`. Test cần matching theo event ID/business ID để tránh một event khác làm test thành công nhầm. Timeout của test không hủy listener; hãy dùng ID riêng và cleanup dữ liệu để event đến muộn không ảnh hưởng test khác.

## 19. Xử lý sự cố theo từng chặng

Khi consumer không nhận được event, điều tra từ đầu luồng đến cuối:

1. **Producer:** command có được chấp nhận và domain transition có commit không?
2. **Publish:** event có được publish với đúng type/version không?
3. **Transaction:** listener yêu cầu AFTER_COMMIT có transaction đã commit không?
4. **Registry:** publication của listener đang hoàn tất hay còn incomplete?
5. **Executor:** task có đang chờ queue hoặc thread không?
6. **Adapter:** event có được chọn để externalize và serialize thành công không?
7. **Broker:** message có được route đến đúng queue/topic không?
8. **Consumer:** consumer có đang chạy và đọc đúng destination không?
9. **Contract:** deserialize/version validation có thành công không?
10. **Processing:** inbox, transaction và business logic có hoàn tất không?
11. **Acknowledgement:** message đã được ack/offset commit đúng thời điểm chưa?

Không kết luận “event bị mất” chỉ từ việc consumer chưa thấy message. Nó có thể đang chờ commit, nằm trong executor queue, bị route sai, nằm trong retry/DLQ hoặc consumer đang xử lý nhưng chưa ack.

## 20. Ví dụ luồng OrderConfirmed hoàn chỉnh

Giả sử Orders xác nhận đơn và Inventory cần giữ hàng, Notification cần gửi thông báo, Analytics cần cập nhật projection.

**Producer**
- Orders kiểm tra đơn ở trạng thái PAID.
- Orders cập nhật trạng thái CONFIRMED trong transaction.
- Orders tạo OrderConfirmed với event ID, order ID, aggregate version và occurredAt.
- Orders publish event.

**Internal consumers**
- InventoryListener chạy sau commit và yêu cầu Inventory giữ hàng.
- NotificationListener tạo notification operation.
- AnalyticsListener cập nhật projection.
- Registry theo dõi publication riêng cho từng listener.

**Externalization**
- Adapter chuyển OrderConfirmed thành message theo contract tích hợp nếu hệ thống ngoài cần biết.
- Message được serialize, gắn metadata và gửi đến broker.
- Broker route/lưu message theo cấu hình.

**External consumer**
- Consumer xác thực schema version.
- Consumer kiểm tra inbox/idempotency.
- Consumer cập nhật dữ liệu trong transaction.
- Consumer ack message sau khi xử lý theo semantics đã chọn.

Không nên hiểu rằng API confirm order phải chờ cả ba listener và external consumer hoàn tất. Nếu giữ hàng là điều kiện bắt buộc để xác nhận đơn, cần workflow có trạng thái pending hoặc điều phối đồng bộ phù hợp. Nếu notification và analytics là phản ứng độc lập, chúng có thể hoàn tất sau response.

## 21. Checklist thiết kế luồng producer đến consumer

- [ ] Producer sở hữu domain transition và chỉ phát sự thật đã xảy ra.
- [ ] Event contract có tên, semantics, ID, version và payload rõ.
- [ ] Publish point và transaction boundary được tài liệu hóa.
- [ ] Listener đồng bộ, AFTER_COMMIT và async được phân biệt.
- [ ] Event Publication Registry được cấu hình theo yêu cầu phục hồi.
- [ ] Mỗi listener chỉ thực hiện trách nhiệm của module sở hữu.
- [ ] Externalization adapter và destination được xác định rõ.
- [ ] Broker routing, retention, acknowledgement và retry có policy.
- [ ] Consumer xác thực schema/version và metadata.
- [ ] Consumer idempotent và có inbox/unique constraint khi cần.
- [ ] Ordering/sequence được xử lý theo aggregate hoặc partition.
- [ ] Outbox được cân nhắc cho dual-write producer-to-broker.
- [ ] Retry có timeout, backoff, jitter, budget và DLQ.
- [ ] Logs/traces/metrics liên kết được các chặng.
- [ ] Test bao phủ producer, transaction, listener, registry, broker và consumer.
- [ ] Runbook phân biệt incomplete publication, outbox backlog và broker lag.

## 22. Nguyên tắc giữ luồng event đáng tin cậy

Luồng từ producer đến consumer gồm nhiều boundary. Producer sở hữu sự thật nghiệp vụ và event contract; application event mechanism phân phối đến listener; Event Publication Registry theo dõi publication nội bộ; adapter externalization chuyển event thành message; broker vận chuyển; consumer xác thực contract, chống duplicate và cập nhật dữ liệu của mình.

Độ tin cậy đến từ việc làm rõ transaction, delivery semantics, idempotency, ordering, retry và observability tại từng boundary. Không một annotation, registry hoặc broker đơn lẻ bảo đảm toàn bộ workflow. Khi mỗi chặng có owner, contract, trạng thái và cách phục hồi rõ ràng, application events có thể kết nối các module Spring Modulith và hệ thống bên ngoài mà vẫn giữ được ranh giới nghiệp vụ.
