# Checklist thiết kế event

## Mục tiêu

Application events là một cơ chế quan trọng để các module Spring Modulith thông báo cho nhau về những thay đổi nghiệp vụ. Event được thiết kế tốt giúp module phát và nhận giao tiếp qua contract rõ ràng, giảm phụ thuộc trực tiếp và giữ ranh giới sở hữu dữ liệu. Event được thiết kế thiếu ngữ nghĩa, payload mơ hồ hoặc delivery không có quy tắc có thể tạo duplicate side effect, phụ thuộc vòng, backlog và khó khăn khi thay đổi phiên bản.

Bài này tổng hợp một **checklist thiết kế event** có thể dùng khi tạo event mới, review pull request, externalize event ra broker hoặc đánh giá một luồng event đang chạy production. Checklist bao quát vòng đời từ ý nghĩa nghiệp vụ, producer/consumer, transaction, payload, reliability, bảo mật đến kiểm thử và vận hành.

Sau bài học, bạn có thể:

- Xác định event có thực sự là cách giao tiếp phù hợp.
- Làm rõ producer owner, consumer và business semantics.
- Thiết kế payload, metadata, version và transaction boundary.
- Chọn delivery, ordering, idempotency, retry và recovery policy.
- Bảo vệ dữ liệu và giữ contract tương thích khi hệ thống tiến hóa.
- Review event bằng checklist có thể kiểm chứng và ghi nhận quyết định thiết kế.

## 1. Bắt đầu từ nhu cầu nghiệp vụ

Trước khi tạo class event, hãy xác định vấn đề mà event cần giải quyết. Không nên phát event chỉ vì muốn tránh một lời gọi method hoặc vì hệ thống đã có broker.

### Câu hỏi định hướng

- Có một sự kiện nghiệp vụ đã xảy ra mà module khác cần biết không?
- Consumer cần phản ứng độc lập hay producer cần nhận kết quả ngay để tiếp tục use case?
- Các module có thể giao tiếp qua API công khai hoặc command rõ ràng hơn không?
- Có cần xử lý bất đồng bộ, fan-out hoặc tích hợp với hệ thống ngoài không?
- Nếu consumer tạm ngừng, event có cần được lưu và xử lý lại không?
- Ai sở hữu trạng thái nghiệp vụ và quyết định cuối cùng?

Event phù hợp khi producer công bố một fact và consumer có thể phản ứng mà không cần producer biết implementation của consumer. Nếu producer cần một kết quả đồng bộ để quyết định có tiếp tục hay không, application API hoặc command-response có thể phù hợp hơn.

### Event, command và query

| Message | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Command | Yêu cầu một owner thực hiện hành động. | `ReserveInventory`, `CapturePayment`. |
| Event | Thông báo một fact đã xảy ra. | `InventoryReserved`, `PaymentCaptured`. |
| Query | Yêu cầu dữ liệu hiện tại. | `GetOrderDetails`, `FindAvailableStock`. |

Tên event nên mô tả điều đã xảy ra, thường ở dạng quá khứ. `OrderPlaced` diễn đạt một đơn đã được tạo; `PlaceOrder` là yêu cầu tạo đơn. Phân biệt đúng giúp consumer không nhầm một yêu cầu đang chờ với kết quả đã hoàn tất.

## 2. Checklist ownership và ranh giới module

Mỗi event cần một producer owner rõ ràng. Owner chịu trách nhiệm về ý nghĩa, điều kiện phát và contract; consumer sở hữu cách phản ứng trong phạm vi dữ liệu của mình.

### Producer cần xác định

- [ ] Module và component nào có quyền phát event?
- [ ] Use case hoặc domain transition nào tạo event?
- [ ] Module nào sở hữu aggregate/dữ liệu liên quan?
- [ ] Ai review thay đổi payload và version?
- [ ] Event có được phát từ nhiều use case không; nếu có, semantics có giống nhau không?
- [ ] Có phân biệt event nội bộ và integration event không?

### Consumer cần xác định

- [ ] Những listener/module/service nào tiêu thụ event?
- [ ] Mỗi consumer dùng event để làm gì?
- [ ] Consumer có cập nhật dữ liệu do chính nó sở hữu không?
- [ ] Consumer có phát event tiếp theo không?
- [ ] Có event flow cycle hoặc chuỗi phản hồi không?
- [ ] Consumer nào cần xử lý theo thứ tự hoặc có thể chạy song song?

### Nguyên tắc ranh giới

Module không nên truy cập repository hoặc entity nội bộ của module khác chỉ vì nó nhận event. Consumer dùng contract công khai để quyết định hành vi; module sở hữu dữ liệu chịu trách nhiệm xác thực và thực hiện transition.

Ví dụ với luồng đặt hàng:

| Module | Dữ liệu sở hữu | Event liên quan |
| --- | --- | --- |
| Orders | Trạng thái đơn hàng | Phát `OrderPlaced`, nhận kết quả reservation/payment. |
| Inventory | Tồn kho và reservation | Nhận `OrderPlaced`, phát `InventoryReserved` hoặc `InventoryRejected`. |
| Payments | Giao dịch thanh toán | Nhận yêu cầu thanh toán, phát `PaymentCaptured` hoặc `PaymentRejected`. |
| Shipping | Shipment và trạng thái giao hàng | Nhận yêu cầu giao, phát `ShipmentCreated` hoặc `ShipmentFailed`. |

Không để nhiều module cùng quyết định trạng thái authoritative của một aggregate. Nếu workflow nhiều bước cần điều phối, cân nhắc process manager/saga có state rõ ràng.

## 3. Checklist semantics và trigger

Event contract phải trả lời chính xác “điều gì đã xảy ra?”. Một tên dễ đọc chưa đủ nếu người viết và consumer hiểu khác nhau.

- [ ] Mô tả event bằng một câu nghiệp vụ rõ ràng.
- [ ] Xác định event biểu diễn yêu cầu, quyết định hay kết quả đã hoàn tất.
- [ ] Ghi precondition và điều kiện phát.
- [ ] Nêu rõ điều event không có nghĩa là gì.
- [ ] Xác định event phát một lần cho mỗi transition hay có thể phát lại.
- [ ] Phân biệt thời điểm nghiệp vụ xảy ra với thời điểm publish/receive.
- [ ] Không phát event chỉ vì một entity được save nếu không có transition nghiệp vụ mới.

Ví dụ:

> `OrderPlaced` được phát khi use case PlaceOrder hoàn tất validation, lưu trạng thái PLACED và transaction tạo đơn commit thành công. Event không khẳng định hàng đã được giữ hoặc thanh toán đã hoàn tất.

Mô tả này giúp consumer hiểu rằng Inventory có thể bắt đầu giữ hàng sau event, nhưng không được coi đơn là đã thanh toán.

## 4. Checklist transaction và thời điểm publish

Transaction boundary quyết định event phản ánh dữ liệu đã commit hay mới chỉ là ý định đang được xử lý.

- [ ] Producer có chạy trong transaction không?
- [ ] Event được publish ở đâu trong use case?
- [ ] Listener xử lý đồng bộ hay bất đồng bộ?
- [ ] Listener có chạy sau commit không?
- [ ] Điều gì xảy ra khi transaction publisher rollback?
- [ ] Publication được theo dõi bởi Event Publication Registry không?
- [ ] Externalization có dùng outbox hoặc cơ chế bền vững tương đương không?
- [ ] Có kiểm thử commit, rollback và crash window không?

### Ví dụ trong Spring Modulith

```java
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
    public UUID place(PlaceOrder command) {
        Order order = Order.place(command);
        orders.save(order);
        events.publishEvent(OrderPlaced.from(order));
        return order.getId();
    }
}
```

Publisher phát event trong transaction. Listener được cấu hình theo semantics tương ứng, ví dụ `@ApplicationModuleListener` cho xử lý module bất đồng bộ sau commit. Cần kiểm tra behavior của phiên bản Spring Modulith đang dùng và transaction manager của ứng dụng; không suy luận rằng mọi listener đều chạy cùng transaction publisher.

### Phân biệt trách nhiệm của các cơ chế

| Cơ chế | Vai trò |
| --- | --- |
| `ApplicationEventPublisher` | Phát application event trong Spring application context. |
| `@ApplicationModuleListener` | Khai báo listener module với mô hình xử lý bất đồng bộ/sau commit của Spring Modulith. |
| `@TransactionalEventListener` | Gắn listener với transaction phase của Spring. |
| Event Publication Registry | Theo dõi publication tới listener được quản lý và trạng thái hoàn tất. |
| Outbox | Lưu message cần externalize cùng transaction nghiệp vụ để dispatcher gửi sau. |

Các cơ chế có thể kết hợp nhưng không thay thế nhau. Event Publication Registry không mặc định là event store lưu toàn bộ lịch sử nghiệp vụ; broker cũng không thay thế transaction database của producer.

## 5. Checklist payload và contract

Payload nên tối thiểu nhưng đủ để consumer thực hiện trách nhiệm của nó. Không gửi toàn bộ aggregate chỉ để consumer tự tìm field cần dùng.

- [ ] Có event type/name ổn định và mô tả rõ.
- [ ] Có `eventId` duy nhất cho mỗi event.
- [ ] Có aggregate/business key nếu consumer cần định danh đối tượng.
- [ ] Có aggregate version/sequence nếu thứ tự thay đổi quan trọng.
- [ ] Field có kiểu, required/optional và nullability rõ.
- [ ] Timestamp có format/timezone và semantics rõ.
- [ ] Tiền, số lượng và đơn vị đo có precision/unit rõ.
- [ ] Enum có quy tắc xử lý giá trị chưa biết.
- [ ] Không expose entity, lazy proxy hoặc object graph nội bộ.
- [ ] Không chứa credential, token, private key hoặc dữ liệu nhạy cảm không cần thiết.

### Ví dụ DTO

```java
public record OrderPlacedV1(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        Instant occurredAt,
        String currency,
        long totalAmountMinor) {}
```

DTO này thể hiện event contract bên ngoài. `totalAmountMinor` dùng số nguyên thay cho floating point; contract cần quy định rõ cách diễn giải đơn vị nhỏ nhất theo `currency`.

### Ví dụ JSON envelope

```json
{
  "eventType": "com.example.orders.order-placed",
  "schemaVersion": 1,
  "eventId": "f29fdfb4-0f4c-49f9-9e9d-6ec61f64dba8",
  "occurredAt": "2026-11-25T08:30:00Z",
  "producer": "orders",
  "correlationId": "6e0a6c4b-54f6-4a74-a1c0-4b98b1c39d60",
  "payload": {
    "orderId": "7b2f42b0-80a0-4f3c-87c5-93a8d64b1a2e",
    "aggregateVersion": 1,
    "currency": "VND",
    "totalAmountMinor": 125000
  }
}
```

Đây là envelope minh họa do ứng dụng định nghĩa, không phải format mặc định của Spring Modulith. Nếu một phần metadata nằm trong broker headers, tài liệu cần chỉ rõ nguồn chuẩn và quy tắc mapping.

## 6. Checklist metadata và khả năng truy vết

Metadata hỗ trợ nối các bước trong workflow và điều tra event bị trễ, trùng hoặc sai thứ tự.

| Metadata | Mục đích | Lưu ý |
| --- | --- | --- |
| `eventId` | Định danh event | Giữ ổn định khi retry cùng event. |
| `correlationId` | Nối các hoạt động trong một workflow | Có thể được tạo từ request/process ban đầu. |
| `causationId` | Xác định event/command trực tiếp gây ra event hiện tại | Hữu ích khi dựng chuỗi nguyên nhân. |
| `aggregateId` | Định danh aggregate | Dùng làm key nếu cần partition theo aggregate. |
| `aggregateVersion` | Xác định version state | Phát hiện stale event hoặc version gap. |
| `eventType` | Xác định loại event | Phải ổn định và có namespace phù hợp. |
| `schemaVersion` | Chọn schema/mapper | Có một nguồn version chuẩn. |
| `occurredAt` | Thời điểm nghiệp vụ | Không đồng nhất với `publishedAt` hoặc `receivedAt`. |

Không đưa payload nhạy cảm vào trace. Tránh dùng event ID, aggregate ID hoặc correlation ID làm metric label có cardinality không giới hạn; dùng log/trace có kiểm soát để tra cứu từng event.

## 7. Checklist delivery và reliability

Thiết kế phải nói rõ event được giao theo semantics nào và hệ thống phục hồi ra sao khi process hoặc dependency lỗi.

- [ ] Xác định delivery semantics thực tế: at-most-once, at-least-once hoặc guarantee cụ thể theo transport.
- [ ] Consumer có idempotent khi nhận cùng event nhiều lần không?
- [ ] Có inbox/unique constraint cho side effect quan trọng không?
- [ ] Có retry policy với số lần, backoff, jitter và deadline không?
- [ ] Phân biệt lỗi transient và permanent.
- [ ] Có DLQ/quarantine và quy trình replay không?
- [ ] Có xử lý publication chưa hoàn tất sau restart không?
- [ ] Có giới hạn queue/concurrency và backpressure không?
- [ ] Có xác định hành vi khi broker hoặc database unavailable không?

### Idempotency

Event có thể được giao lại sau crash hoặc retry. Consumer nên ghi nhận event đã xử lý cùng transaction với thay đổi nghiệp vụ:

```text
BEGIN TRANSACTION
  insert inbox(listener_id, event_id) -- unique constraint
  update business state
  insert next event into outbox (if needed)
COMMIT
```

Nếu insert inbox gặp duplicate key, consumer có thể kết luận event đã được xử lý theo policy. Cách này bền vững hơn một `Set` trong bộ nhớ, vốn mất khi restart và không chia sẻ giữa nhiều instance.

### Retry và quarantine

Retry chỉ phù hợp với lỗi có khả năng phục hồi. Lỗi dữ liệu/schema hoặc authorization thường cần sửa nguyên nhân trước khi thử lại. Khi hết retry budget, chuyển event sang quarantine/DLQ kèm event ID, correlation, lỗi và thông tin cần thiết để điều tra; không lưu secret trong failure record.

Không retry vô hạn vì có thể khuếch đại quá tải và che giấu lỗi contract.

## 8. Checklist ordering và event flow

Không mặc định event được xử lý theo thứ tự publish. Phải xác định thứ tự nào có ý nghĩa nghiệp vụ và phạm vi cần bảo đảm.

- [ ] Có yêu cầu thứ tự toàn hệ thống hay chỉ theo aggregate?
- [ ] Event có aggregate ID và version phù hợp không?
- [ ] Broker partition/queue key có giữ thứ tự cần thiết không?
- [ ] Consumer có dispatch bất đồng bộ làm completion order thay đổi không?
- [ ] Consumer xử lý event cũ, duplicate và version gap thế nào?
- [ ] Event flow có chu trình hoặc phản hồi ping-pong không?
- [ ] Workflow có terminal state và timeout rõ không?

Ví dụ, Kafka có thể giữ thứ tự record trong cùng partition, nhưng nếu consumer đẩy record sang thread pool và xử lý song song, side effect vẫn có thể hoàn tất ngược thứ tự. Nếu thứ tự theo `orderId` là bắt buộc, cần key theo aggregate và giữ xử lý tuần tự theo key hoặc kiểm tra version ở consumer.

### Phòng ngừa phụ thuộc vòng

Vẽ event flow graph gồm producer, consumer và event tiếp theo. Xác định module sở hữu trạng thái và chỉ phát event khi có transition mới. Với workflow nhiều bước, dùng process manager/saga có state, step, retry budget và terminal state. `ApplicationModules.verify()` giúp kiểm tra một số dependency rule trong mã nguồn nhưng không thay thế phân tích runtime event graph.

## 9. Checklist bảo mật và quyền riêng tư

Event thường được lưu trong broker, log, archive hoặc hệ thống phân tích lâu hơn request gốc. Payload cần được xem như dữ liệu có vòng đời riêng.

- [ ] Payload chỉ chứa dữ liệu consumer thực sự cần.
- [ ] Có phân loại dữ liệu cá nhân, tài chính và dữ liệu nhạy cảm.
- [ ] Không gửi password, token, API key hoặc private key trong event/header.
- [ ] Xác định TLS/mTLS, authentication và authorization ở transport.
- [ ] Producer chỉ có quyền publish destination cần thiết.
- [ ] Consumer chỉ có quyền đọc topic/queue cần thiết.
- [ ] Có retention, archive và deletion policy phù hợp.
- [ ] Log/trace redact dữ liệu nhạy cảm.
- [ ] Có quy tắc xử lý dữ liệu khi replay hoặc đưa vào DLQ.

Credential của Kafka, RabbitMQ, Schema Registry hoặc database phải được cấp qua secret manager/workload identity theo policy của nền tảng. Event không phải kênh chuyển credential giữa các module.

## 10. Checklist versioning và compatibility

Event contract có thể được consumer sử dụng lâu dài. Thay đổi cấu trúc và semantics đều cần được đánh giá tương thích.

- [ ] Có event type và schema version rõ ràng.
- [ ] Có nguồn version chuẩn giữa payload, header, schema registry và topic.
- [ ] Consumer cũ có đọc được payload mới không?
- [ ] Consumer mới có đọc được payload cũ không?
- [ ] Thay đổi có làm đổi unit, timezone, enum hoặc business meaning không?
- [ ] Có payload fixture của các version còn hỗ trợ không?
- [ ] Có upcaster/adapter nếu cần đọc lịch sử không?
- [ ] Có consumer inventory và owner xác nhận trước breaking change không?
- [ ] Có deprecation window và điều kiện loại bỏ version cũ không?

### Chiến lược expand-migrate-contract

1. **Expand:** triển khai consumer đọc được cả V1 và V2 trong khi producer vẫn phát V1.
2. **Migrate:** chuyển producer sang V2 hoặc dual-publish có kiểm soát; theo dõi consumer và side effect.
3. **Contract:** ngừng V1 khi không còn consumer cần nó và đã hết retention/replay window.

Không dual-publish nếu consumer có thể xử lý cùng business event hai lần mà không có identity/deduplication rõ ràng.

## 11. Checklist kiểm thử

Test nên xác minh contract ở nhiều lớp, từ logic producer tới transport và consumer.

| Loại test | Câu hỏi cần trả lời |
| --- | --- |
| Unit test producer | Use case hợp lệ có phát đúng event/payload không? |
| Module test | Spring Modulith có nối đúng listener trong ranh giới module không? |
| Transaction test | Commit/rollback có tạo đúng behavior không? |
| Serialization test | Payload round-trip có giữ đúng type, unit và timestamp không? |
| Contract test | Consumer có đọc được các version được hỗ trợ không? |
| Broker integration test | Routing, ack, redelivery, partition và DLQ có đúng không? |
| Failure test | Retry, duplicate, restart và dependency outage có an toàn không? |
| Architecture test | Module dependency có tuân thủ boundary rule không? |

Với listener bất đồng bộ, chờ điều kiện hoàn tất bằng Scenario, latch, future hoặc Awaitility có timeout. Tránh `Thread.sleep()` vì test dễ phụ thuộc tốc độ máy/CI.

Với broker thật, dùng Testcontainers hoặc môi trường integration phù hợp để xác minh semantics phụ thuộc Kafka/RabbitMQ. Mock/fake phù hợp cho logic mapping và policy nhưng không chứng minh broker protocol, acknowledgement hoặc routing.

## 12. Checklist observability và vận hành

Một event cần có đủ dấu vết để operator xác định nó được phát, giao, xử lý và hoàn tất ở đâu.

- [ ] Log/trace có event ID, correlation ID, causation ID và event type.
- [ ] Có producer/consumer/module identity và aggregate version khi cần.
- [ ] Có metric publish rate, completion rate và error rate.
- [ ] Có latency histogram theo listener hoặc event flow.
- [ ] Theo dõi publication incomplete và tuổi publication lâu nhất.
- [ ] Theo dõi executor queue, rejected task và consumer lag.
- [ ] Theo dõi retry, duplicate, DLQ/quarantine và event age.
- [ ] Có dashboard/runbook và owner trực vận hành.
- [ ] Có cảnh báo theo SLO, backlog age và dependency health.

Tên metric có thể theo convention như `event_published_total`, `event_listener_completed_total`, `event_listener_failed_total` hoặc `event_publication_incomplete`. Đây là gợi ý đặt tên; không giả định mọi metric được Spring Modulith tự cung cấp. Instrument bằng Micrometer/observability stack của ứng dụng.

## 13. Ví dụ review một event mới

Giả sử module Orders muốn phát `OrderPlaced`. Reviewer có thể đi qua các bước sau:

1. **Mục đích:** Inventory cần biết đơn đã được tạo để bắt đầu quy trình giữ hàng; analytics cần cập nhật dữ liệu báo cáo.
2. **Owner:** Orders sở hữu trạng thái đơn và quyết định phát event.
3. **Semantics:** Event chỉ có nghĩa đơn đã commit ở trạng thái PLACED.
4. **Payload:** Gồm event ID, order ID, aggregate version, occurredAt, currency, total amount và các dòng hàng tối thiểu.
5. **Transaction:** Event được phát trong transaction; listener module xử lý theo after-commit semantics đã cấu hình.
6. **Delivery:** Consumer chấp nhận at-least-once và dùng event ID để idempotency.
7. **Ordering:** Event của cùng order dùng order ID làm key nếu broker hỗ trợ partitioning; consumer vẫn kiểm tra version.
8. **Security:** Không đưa thông tin thanh toán nhạy cảm hoặc credential vào payload.
9. **Compatibility:** Contract V1 có schema và fixture; thay đổi bắt buộc tạo version mới theo migration plan.
10. **Testing/operations:** Có producer/module/contract test, metric completion, retry và runbook DLQ.

Nếu một mục chưa có câu trả lời, reviewer ghi rõ owner và hành động cần hoàn tất trước khi công bố event.

## 14. Mẫu decision record cho event

Đối với event quan trọng hoặc externalized, ghi một decision record ngắn để lưu lại lý do thiết kế:

```yaml
event: OrderPlaced
owner: orders
meaning: Đơn hàng đã được tạo hợp lệ và transaction đã commit.
producer:
  component: OrderApplicationService.place
  transaction: order creation transaction
consumers:
  - module: inventory
    purpose: Bắt đầu giữ hàng
  - service: order-analytics
    purpose: Cập nhật dữ liệu phân tích
contract:
  version: 1
  schema: contracts/orders/order-placed/v1/schema.json
  delivery: at-least-once
  idempotency: eventId
  ordering: per-order aggregate key/version
security:
  classification: internal-business-data
  secretsIncluded: false
operations:
  retryPolicy: bounded-backoff
  deadLetter: orders.events.dlq
```

Đây là mẫu minh họa. Các giá trị như destination, classification, retry policy và schema path phải được xác nhận theo môi trường thực tế; không sao chép mẫu thành cấu hình production mà chưa review.

## 15. Những dấu hiệu cần dừng review

Không nên công bố event khi còn một trong các vấn đề sau:

- Không xác định được module owner hoặc ý nghĩa event.
- Event name thực chất là command nhưng không có owner xử lý.
- Payload chứa entity nội bộ hoặc dữ liệu nhạy cảm không có lý do.
- Không rõ transaction/commit semantics.
- Consumer có thể tạo side effect lặp nhưng không có idempotency.
- Có event cycle không có state machine hoặc điều kiện kết thúc.
- Breaking change không có migration/compatibility plan.
- Không có cách quan sát publication, listener failure hoặc backlog.
- Credential hoặc quyền broker được cấp quá rộng.
- Không có test chứng minh contract quan trọng.

Các vấn đề này cần owner và phương án xử lý cụ thể trước khi event được đưa vào luồng production.

## 16. Checklist tổng hợp trước khi công bố

### Nghiệp vụ và ownership

- [ ] Event biểu diễn một fact đã xảy ra.
- [ ] Producer owner, consumer và mục đích được ghi rõ.
- [ ] Trigger, precondition và transaction boundary được xác định.
- [ ] Mỗi aggregate/state có owner authoritative.
- [ ] Event flow không tạo vòng lặp ngoài ý muốn.

### Contract và dữ liệu

- [ ] Event type, version và schema source of truth được xác định.
- [ ] Payload tối thiểu, có type/unit/nullability/semantics rõ.
- [ ] Có event ID, correlation/causation và aggregate version khi cần.
- [ ] Timestamp và ordering semantics rõ.
- [ ] Không expose implementation nội bộ hoặc secret.

### Reliability và transport

- [ ] Delivery semantics, idempotency và retry được định nghĩa.
- [ ] Có policy DLQ/quarantine/replay.
- [ ] Có bounded concurrency/queue và backpressure phù hợp.
- [ ] Broker routing, key, serializer và ACL đã được xác minh nếu externalize.
- [ ] Có kế hoạch xử lý restart, duplicate và dependency outage.

### Bảo mật và lifecycle

- [ ] Data classification, retention và quyền truy cập rõ.
- [ ] Credential lấy từ secret manager/workload identity.
- [ ] Có compatibility, deprecation và migration plan.
- [ ] Consumer inventory và owner được cập nhật.

### Kiểm thử và vận hành

- [ ] Có unit/module/contract/integration tests phù hợp.
- [ ] Có test commit/rollback, duplicate, retry và ordering khi cần.
- [ ] Có metric, log/trace, dashboard, alert và runbook.
- [ ] Có owner chịu trách nhiệm sau khi triển khai.

## 17. Quy trình áp dụng trong nhóm phát triển

Để checklist trở thành một phần của quy trình thay vì tài liệu tham khảo rời rạc:

1. Khi đề xuất event mới, producer owner mô tả business fact và consumer cần biết.
2. Thiết kế contract cùng module boundary, transaction và delivery semantics.
3. Review payload, metadata, security và version với consumer/platform owner.
4. Viết test chứng minh producer, listener và contract trước khi merge.
5. Bổ sung catalog, schema reference, dashboard và runbook.
6. Khi thay đổi event, đánh giá consumer impact và thực hiện migration có kiểm soát.
7. Sau deploy, theo dõi throughput, latency, backlog, retry và publication incomplete.
8. Định kỳ rà soát event không còn consumer, contract cũ và quyền broker không còn cần thiết.

Checklist thiết kế event không nhằm bắt mọi event phải có cùng độ phức tạp. Event nội bộ đơn giản có thể cần ít metadata và hạ tầng hơn integration event quan trọng. Điều cần giữ nhất quán là ý nghĩa nghiệp vụ, ownership, transaction, contract và cách xử lý lỗi phải phù hợp với mức độ ảnh hưởng của event. Khi những quyết định này được ghi rõ và kiểm thử, application events giúp các module Spring Modulith giao tiếp độc lập mà vẫn có thể kiểm soát tính đúng đắn và vận hành lâu dài.
