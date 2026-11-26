# Danh mục producer

## Mục tiêu

Trong một ứng dụng Spring Modulith, nhiều module có thể phát application event để thông báo rằng một thay đổi nghiệp vụ đã xảy ra. Khi số lượng event và listener tăng lên, việc tìm câu trả lời cho những câu hỏi như “module nào phát event này?”, “event được phát khi nào?”, “dữ liệu nào được gửi ra broker?” hoặc “ai chịu trách nhiệm khi contract thay đổi?” trở nên khó khăn nếu thông tin chỉ nằm rải rác trong source code.

**Danh mục producer (producer catalog)** là tài liệu tập trung mô tả các module và thành phần phát event, event contract mà chúng phát ra, điều kiện phát, phạm vi tiêu thụ và trách nhiệm vận hành. Danh mục giúp developer, reviewer và operator khám phá luồng event, đánh giá ảnh hưởng khi thay đổi contract và tìm đúng owner khi có sự cố.

Sau bài học, bạn có thể:

- Phân biệt producer, event type, listener và broker destination.
- Thiết kế các trường thông tin cần có trong producer catalog.
- Ghi nhận producer nội bộ và producer externalize event qua broker.
- Mô tả trigger, transaction boundary, payload, version và ownership.
- Tổ chức catalog để dễ tìm kiếm, review và cập nhật theo source code.
- Dùng catalog trong thay đổi contract, kiểm thử và vận hành event.

## 1. Producer là gì?

Producer là thành phần tạo và phát một event. Trong Spring Modulith, producer thường là application service, domain service hoặc component trong module gọi `ApplicationEventPublisher` sau khi một thay đổi nghiệp vụ được chấp nhận.

Ví dụ:

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

Trong ví dụ, module Đơn hàng là producer của `OrderPlaced`. `ApplicationEventPublisher` là cơ chế phát event; nó không phải producer nghiệp vụ. Producer cần được ghi nhận theo module và use case đã quyết định phát event.

### Producer không đồng nghĩa với event type

Một producer có thể phát nhiều event type. Ngược lại, cùng một event type có thể được phát từ nhiều use case hoặc nhiều thành phần nếu contract cho phép. Catalog nên ghi rõ quan hệ producer-event thay vì chỉ liệt kê tên class.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Producer | Module/thành phần tạo và phát event. |
| Event type | Tên và contract mô tả điều đã xảy ra. |
| Listener/consumer | Thành phần nhận và xử lý event. |
| Destination | Topic, queue, exchange hoặc endpoint nhận event externalized. |
| Event Publication Registry | Cơ chế theo dõi publication tới listener được Spring Modulith quản lý. |

Producer catalog tập trung vào nguồn phát. Listener catalog hoặc event flow map có thể liên kết tới cùng event để mô tả đầu nhận và luồng xử lý hoàn chỉnh.

## 2. Vì sao cần producer catalog?

Khi một event được nhiều module sử dụng, thay đổi ở producer có thể ảnh hưởng tới nhiều consumer. Nếu không biết danh sách producer và contract, đội phát triển khó xác định phạm vi ảnh hưởng và dễ bỏ sót consumer.

Catalog giúp:

- **Khám phá:** tìm module phát event, use case và event type liên quan.
- **Quản lý contract:** xác định schema/version, field, semantics và chính sách tương thích.
- **Phân tích ảnh hưởng:** biết module hoặc hệ thống nào có thể bị tác động khi producer thay đổi.
- **Review:** kiểm tra event có đúng thời điểm nghiệp vụ, có dữ liệu cần thiết và không lộ thông tin không cần thiết.
- **Vận hành:** tìm owner, correlation metadata, destination và dashboard khi event bị trễ hoặc lỗi.
- **Onboarding:** giúp developer mới hiểu cách module công bố thay đổi nghiệp vụ.
- **Governance:** hỗ trợ deprecation, versioning, bảo mật và quy trình công bố event mới.

Catalog không thay thế source code, schema registry, API documentation hoặc telemetry. Nó là chỉ mục có cấu trúc, liên kết những thông tin đó thành một góc nhìn có thể tra cứu.

## 3. Những thông tin cần có trong một mục producer

Một mục catalog nên có đủ thông tin để người đọc xác định nguồn phát, thời điểm phát và cách consumer sử dụng event.

| Nhóm thông tin | Trường gợi ý | Mục đích |
| --- | --- | --- |
| Định danh | `producerId`, `module`, `component`, `useCase` | Xác định producer duy nhất và vị trí sở hữu. |
| Event | `eventType`, `eventVersion`, `description` | Xác định event và ý nghĩa nghiệp vụ. |
| Trigger | `trigger`, `preconditions`, `businessOutcome` | Giải thích điều gì khiến event được phát. |
| Transaction | `transactionBoundary`, `publishPhase` | Làm rõ event được phát trong transaction nào và listener xử lý ở phase nào. |
| Payload | `schema`, `fields`, `sensitivity` | Mô tả cấu trúc, ý nghĩa và phân loại dữ liệu. |
| Delivery | `deliveryMode`, `publicationMechanism`, `idempotencyKey` | Mô tả cách event được chuyển và chống xử lý trùng. |
| Routing | `destination`, `key`, `headers` | Mô tả topic/queue và metadata khi externalize. |
| Ownership | `ownerTeam`, `contact`, `sourceLocation` | Xác định người chịu trách nhiệm và nơi tìm implementation. |
| Consumer | `knownConsumers`, `compatibilityPolicy` | Liên kết producer với các bên nhận đã biết. |
| Operations | `observability`, `retryPolicy`, `retention` | Hỗ trợ theo dõi và điều tra sự cố. |
| Lifecycle | `status`, `introducedIn`, `deprecatedSince` | Theo dõi trạng thái phát hành và vòng đời contract. |

Không phải event nào cũng cần mọi trường. Với event nội bộ đơn giản, có thể lược bỏ destination hoặc retention. Với integration event đi qua broker và được nhiều hệ thống tiêu thụ, cần mô tả chi tiết hơn về schema, version, routing, security và lifecycle.

## 4. Mô tả trigger và ý nghĩa nghiệp vụ

Tên event nên mô tả điều đã xảy ra, thường dùng dạng quá khứ như `OrderPlaced`, `PaymentCaptured` hoặc `InventoryReserved`. Trigger trong catalog giải thích chính xác điều kiện nghiệp vụ khiến producer phát event.

Ví dụ mô tả tốt:

> Module Đơn hàng phát `OrderPlaced` sau khi đơn hàng được tạo và transaction ghi đơn commit thành công. Event chỉ được phát khi các dòng hàng và thông tin khách hàng đã vượt qua validation nghiệp vụ.

Mô tả chưa đủ rõ:

> Phát khi có đơn hàng.

Trigger nên trả lời:

- Use case hoặc hành động nào tạo event?
- Điều kiện nghiệp vụ nào phải đúng?
- Event biểu diễn yêu cầu, quyết định hay kết quả đã hoàn tất?
- Event có được phát một lần cho mỗi aggregate transition không?
- Có trường hợp event bị phát lại hoặc phát từ tác vụ backfill không?

Phân biệt `PaymentRequested` với `PaymentCaptured`: event đầu mô tả yêu cầu được gửi, event sau mô tả khoản thanh toán đã được xác nhận. Nếu catalog không làm rõ semantics, consumer có thể hiểu nhầm một yêu cầu đang chờ thành kết quả thành công.

## 5. Mô tả transaction boundary và thời điểm phát

Thời điểm publish ảnh hưởng tới ý nghĩa và độ tin cậy của event. Catalog nên nêu rõ:

- Producer có chạy trong transaction không?
- Event được publish trước hay sau khi thay đổi dữ liệu commit?
- Listener xử lý đồng bộ hay bất đồng bộ?
- Listener có dùng `@ApplicationModuleListener` hoặc `@TransactionalEventListener` không?
- Publication được theo dõi bởi Event Publication Registry không?
- Có externalization qua broker hoặc outbox không?

Ví dụ:

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| `transactionBoundary` | Transaction tạo đơn hàng của module Orders. |
| `publishPhase` | Publish application event trong transaction; listener module xử lý sau commit. |
| `listenerMode` | `@ApplicationModuleListener`, bất đồng bộ. |
| `publicationTracking` | Event Publication Registry theo dõi publication tới listener được quản lý. |

Không ghi “event chắc chắn được giao đúng một lần” chỉ vì producer dùng transaction. Event có thể được xử lý lại sau crash window hoặc resubmission. Hãy mô tả semantics thực tế và yêu cầu idempotency ở consumer.

### Phân biệt nội bộ và externalized event

Application event nội bộ được publish trong Spring application context. Nếu event được externalize, adapter sẽ chuyển event sang transport như Kafka hoặc RabbitMQ. Catalog cần thể hiện cả event type nội bộ và integration contract/destination tương ứng.

Ví dụ:

```java
@Externalized("orders")
public record OrderPlacedIntegrationEvent(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {}
```

`@Externalized` đánh dấu event cần externalize theo cấu hình Spring Modulith/integration đang dùng. Nó không tự mô tả toàn bộ cấu hình broker, serializer hoặc security; những thông tin đó cần được ghi ở phần routing/transport.

## 6. Mô tả event contract và payload

Catalog nên liên kết tới schema hoặc tài liệu contract chuẩn. Nếu schema nằm trong source control hoặc Schema Registry, ghi reference/version thay vì sao chép nhiều bản có thể lệch nhau.

Ví dụ event contract:

```java
public record OrderPlacedV1(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt,
        long aggregateVersion) {}
```

Các field quan trọng cần giải thích semantics:

| Field | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `eventId` | Định danh một lần phát event nghiệp vụ. | Ổn định khi retry cùng event; dùng để deduplicate. |
| `orderId` | Aggregate ID của đơn hàng. | Không được tái sử dụng cho đơn khác. |
| `customerId` | Tham chiếu khách hàng. | Consumer không nên suy ra dữ liệu khách hàng ngoài contract. |
| `totalAmountMinor` | Tổng tiền theo đơn vị nhỏ nhất của currency. | Không dùng floating point; diễn giải cùng `currency`. |
| `currency` | Mã tiền tệ. | Theo quy tắc mã được contract công bố. |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra. | UTC/Instant; phân biệt với thời điểm publish. |
| `aggregateVersion` | Version trạng thái aggregate tại thời điểm phát. | Dùng phát hiện event cũ hoặc gap nếu semantics yêu cầu. |

Ngoài tên và kiểu, catalog cần mô tả field bắt buộc/tùy chọn, default, đơn vị đo, timezone, enum và quy tắc null. Đặc biệt, không để tên `amount` mà không nói rõ đơn vị tiền hoặc tên `timestamp` mà không nói rõ thời điểm được đo.

### Phân loại dữ liệu

Ghi rõ payload có chứa dữ liệu cá nhân, dữ liệu tài chính, bí mật hoặc thông tin nội bộ nhạy cảm không. Với mỗi nhóm, nêu mục đích sử dụng, yêu cầu tối thiểu hóa, quyền truy cập, mã hóa và retention phù hợp.

Không đưa payload thật hoặc dữ liệu cá nhân vào catalog. Dùng ví dụ giả lập và liên kết tới schema đã được kiểm soát quyền truy cập.

## 7. Mô tả routing và transport

Với event externalized, catalog nên ghi:

- Broker/transport: Kafka, RabbitMQ, HTTP hoặc cơ chế khác.
- Topic, exchange, queue hoặc destination logic.
- Key/partition strategy hoặc routing key.
- Serializer và schema format.
- Header như event type, schema version, correlation ID nếu được sử dụng.
- Authentication/authorization và TLS policy ở mức tham chiếu tới tài liệu nền tảng.
- Retry, dead-letter và retention policy có liên quan.

Ví dụ:

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| `transport` | Kafka. |
| `destination` | `orders.events`. |
| `key` | `orderId` để các event của cùng aggregate đi theo partition strategy đã chọn. |
| `serialization` | Avro với schema được quản lý trong Schema Registry. |
| `headers` | `eventId`, `eventType`, `correlationId`. |
| `deliverySemantics` | At-least-once; consumer cần idempotency. |

Không ghi destination chỉ dựa trên tên suy đoán từ annotation. Hãy lấy giá trị từ cấu hình integration thực tế và phân biệt logical destination với topic/queue cuối cùng sau khi áp dụng naming strategy.

## 8. Ownership và vị trí source code

Mỗi producer cần một owner chịu trách nhiệm về ý nghĩa nghiệp vụ và thay đổi contract. Owner thường là team/module sở hữu dữ liệu hoặc use case tạo event.

Catalog nên có:

- Module owner và team chịu trách nhiệm.
- Contact channel hoặc đường dẫn tài liệu nội bộ đã được xác nhận.
- Package/class phát event.
- Use case/application service kích hoạt event.
- File/schema contract hoặc vị trí định nghĩa event.
- Người/nhóm phê duyệt breaking change nếu có chính sách governance.

Source location giúp developer tìm implementation, nhưng catalog không nên phụ thuộc vào line number vì line thay đổi thường xuyên. Dùng package, class, method hoặc link source control có revision khi cần.

Không gán owner theo tên người suy đoán. Nếu chưa xác định team, ghi `owner: TBD` và đưa vào quy trình hoàn thiện catalog.

## 9. Liên kết producer với consumer

Producer catalog có giá trị hơn khi liên kết tới danh sách consumer. Với mỗi event, ghi nhận:

- Listener nội bộ theo module và component.
- Consumer group hoặc service bên ngoài đã biết.
- Mục đích consumer sử dụng event.
- Phiên bản contract consumer hỗ trợ.
- Chính sách xử lý duplicate, out-of-order và retry.
- Mức độ quan trọng/SLO nếu event bị trễ.

Không nên coi danh sách consumer là đầy đủ nếu chưa kiểm tra broker ACL, subscription, deployment inventory và consumer ngoài tổ chức. Có thể đánh dấu mức độ xác minh như `verified`, `declared` hoặc `unknown` để người đọc biết giới hạn.

Ví dụ:

| Consumer | Phạm vi | Mục đích | Trạng thái xác minh |
| --- | --- | --- | --- |
| `inventory` module | Nội bộ | Giữ hàng sau khi đơn được tạo. | Verified trong module test. |
| `order-analytics` service | Kafka | Cập nhật báo cáo đơn hàng. | Declared bởi owner. |
| Data warehouse | Batch/stream | Tổng hợp dữ liệu lịch sử. | Cần xác minh retention và replay. |

Danh sách consumer nên liên kết tới consumer catalog hoặc event flow map nếu hệ thống có các tài liệu đó, tránh sao chép chi tiết ở nhiều nơi.

## 10. Cấu trúc producer catalog

Catalog có thể được lưu dưới dạng Markdown, YAML/JSON có schema hoặc tài liệu sinh từ source metadata. Với dự án nhỏ, Markdown table đủ dễ đọc. Với số lượng lớn và cần tự động hóa, cấu trúc có schema giúp kiểm tra tính đầy đủ và tạo dashboard.

### Ví dụ mục catalog dạng YAML

```yaml
producerId: orders.place-order
module: orders
component: OrderApplicationService
useCase: PlaceOrder
ownerTeam: commerce-orders
event:
  type: com.example.orders.order-placed
  version: 1
  description: Đơn hàng đã được tạo và commit.
  schemaRef: contracts/order-placed-v1.avsc
trigger:
  condition: Command PlaceOrder hợp lệ và aggregate được lưu thành công.
  businessOutcome: Order chuyển sang trạng thái PLACED.
publication:
  mechanism: ApplicationEventPublisher
  transactionBoundary: OrderApplicationService.place
  phase: within-transaction
  tracking: Spring Modulith Event Publication Registry
externalization:
  enabled: true
  transport: kafka
  destination: orders.events
  key: orderId
  deliverySemantics: at-least-once
dataClassification:
  containsPersonalData: false
  containsFinancialData: true
consumers:
  - module: inventory
    purpose: Reserve requested items.
    verification: verified
lifecycle:
  status: active
  introducedIn: 1.0
```

Đây là ví dụ minh họa. Các trường như `phase`, `deliverySemantics` hoặc `containsPersonalData` cần được định nghĩa trong schema catalog của tổ chức; không nên tự tạo nhiều cách viết cho cùng một khái niệm.

### Ví dụ bảng Markdown

| Producer | Event | Trigger | Transaction | Destination | Owner |
| --- | --- | --- | --- | --- | --- |
| `orders.OrderApplicationService.place` | `OrderPlaced.v1` | Đơn hàng được tạo thành công. | Trong transaction tạo đơn; listener nội bộ xử lý sau commit. | `orders.events` | `commerce-orders` |
| `payments.PaymentApplicationService.capture` | `PaymentCaptured.v1` | Cổng thanh toán xác nhận capture. | Sau khi kết quả capture được ghi nhận. | `payments.events` | `commerce-payments` |

## 11. Quy trình tạo và cập nhật catalog

Catalog phải theo kịp source code. Một quy trình hữu ích:

1. Khi thêm event mới, producer owner tạo hoặc cập nhật catalog cùng pull request.
2. Reviewer kiểm tra trigger, semantics, transaction, payload và consumer impact.
3. Nếu externalize, bổ sung destination, schema reference, security và delivery semantics.
4. Liên kết test chứng minh producer phát event đúng trong điều kiện commit/rollback.
5. Khi đổi contract, cập nhật version, compatibility, deprecation và migration plan.
6. Khi xóa producer/event, ghi trạng thái retired và điều kiện dọn dữ liệu lịch sử.
7. Định kỳ đối chiếu catalog với source code và consumer inventory.

### Tự động hóa kiểm tra tính đầy đủ

Có thể dùng static analysis, annotation metadata hoặc convention để phát hiện class có `ApplicationEventPublisher`, event được đánh dấu `@Externalized` và listener tương ứng. Tuy nhiên, scan source code không thể tự hiểu đầy đủ trigger nghiệp vụ, owner, sensitivity hoặc semantics. Những trường này vẫn cần owner xác nhận.

CI có thể kiểm tra:

- Mỗi integration event public có catalog entry.
- Event type/version trong catalog khớp schema reference.
- Producer có owner và source location.
- Externalized event có destination/transport được khai báo.
- Thay đổi schema có compatibility check hoặc migration note.
- Event retired không còn consumer hoạt động theo inventory đã xác minh.

Không nên tự động đánh dấu catalog là đầy đủ chỉ vì scanner tìm thấy mọi lệnh `publishEvent`. Event có thể được phát qua wrapper, helper hoặc domain service; scanner cũng có thể nhầm event nội bộ với event tích hợp.

## 12. Dùng catalog khi thay đổi event contract

Trước khi thay đổi event, tra catalog để xác định:

1. Producer owner và use case phát event.
2. Các consumer nội bộ/ngoài đã biết.
3. Schema version và compatibility policy.
4. Event còn nằm trong broker retention hoặc archive bao lâu.
5. Consumer có replay/backfill hay không.
6. Event chứa dữ liệu nhạy cảm nào.
7. Ai cần tham gia review và thời điểm deprecation.

Nếu thay đổi là breaking, cập nhật catalog theo expand-migrate-contract: công bố version mới, consumer hỗ trợ song song, chuyển publisher, theo dõi traffic version cũ rồi mới retire. Catalog phải phản ánh trạng thái thực tế của quá trình, không chỉ mục tiêu cuối cùng.

## 13. Dùng catalog trong vận hành và điều tra sự cố

Khi event không tới consumer, catalog giúp lần theo đường đi:

- Xác định producer và use case tạo event.
- Kiểm tra điều kiện trigger và transaction commit.
- Xem event type, version, schema và destination.
- Xác định externalization adapter và broker owner.
- Tìm consumer owner, retry/DLQ policy và dashboard.
- Dùng `eventId`, `correlationId` và aggregate ID trong log/trace để truy vết một lần phát cụ thể.

Catalog không chứa trạng thái runtime theo thời gian thực. Nó cần liên kết tới dashboard, log query hoặc runbook thay vì sao chép metric có thể lỗi thời.

Các chỉ số thường liên quan:

- Số event được publish theo event type/producer.
- Số publication chưa hoàn tất và tuổi publication lâu nhất.
- Số message được broker xác nhận, consumer lag và DLQ count.
- Tỷ lệ listener lỗi, retry và duplicate.
- Độ trễ từ business event tới consumer completion.

Không dùng event ID hoặc aggregate ID làm label metric có cardinality cao. Catalog nên hướng dẫn cách tìm định danh trong log/trace có kiểm soát.

## 14. Bảo mật và quản trị catalog

Catalog có thể tiết lộ cấu trúc hệ thống, tên topic, quan hệ giữa module và loại dữ liệu được trao đổi. Vì vậy, phân loại tài liệu và quyền truy cập cần phù hợp với mức nhạy cảm.

- Không lưu payload production, credential, token hoặc private key.
- Không công bố thông tin cá nhân trong ví dụ.
- Ghi phân loại dữ liệu và tham chiếu tới policy mã hóa/retention.
- Chỉ chia sẻ destination nội bộ cho nhóm có nhu cầu.
- Audit thay đổi owner, schema reference, consumer và lifecycle.
- Giữ lịch sử thay đổi để biết contract nào có hiệu lực tại thời điểm phát message.

Catalog cũng cần một owner quản trị cấu trúc chung: tên field, enum trạng thái, format version và quy tắc deprecation. Mỗi producer owner chịu trách nhiệm nội dung event của mình; nhóm platform/architecture có thể duy trì schema và quy trình review chung.

## 15. Những lỗi tài liệu hóa thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ liệt kê tên event | Không biết ai phát, khi nào và vì sao. | Ghi module, component, use case và trigger. |
| Gọi `ApplicationEventPublisher` là producer | Nhầm cơ chế kỹ thuật với owner nghiệp vụ. | Ghi module/thành phần quyết định phát event. |
| Không mô tả transaction boundary | Consumer hiểu nhầm event đã commit hay mới là yêu cầu. | Ghi phase và transaction semantics. |
| Chỉ ghi topic, không ghi schema/version | Consumer không biết payload contract nào được phát. | Liên kết schema và event version. |
| Ghi consumer chưa xác minh như sự thật | Phân tích ảnh hưởng bị thiếu hoặc sai. | Đánh dấu mức độ xác minh và owner xác nhận. |
| Catalog sao chép payload thật | Có nguy cơ lộ dữ liệu nhạy cảm. | Dùng schema và ví dụ giả lập. |
| Catalog không được cập nhật cùng code | Tài liệu nhanh chóng lỗi thời. | Đưa catalog vào review/CI. |
| Scanner tự suy ra semantics | Trigger/owner bị ghi sai. | Yêu cầu producer owner xác nhận thông tin nghiệp vụ. |
| Dùng catalog như dashboard runtime | Thông tin trạng thái bị cũ. | Liên kết tới telemetry/runbook hiện hành. |

## 16. Quy trình áp dụng

Khi xây dựng danh mục producer cho Spring Modulith:

1. Liệt kê module và use case có phát application event.
2. Gắn mỗi event với producer owner, event type và mô tả nghiệp vụ.
3. Ghi trigger, precondition, transaction boundary và publish phase.
4. Liên kết schema/version và mô tả field, đơn vị, timezone, sensitivity.
5. Phân biệt event nội bộ với event externalized; ghi transport, destination, key và headers nếu có.
6. Liệt kê consumer đã biết và đánh dấu mức độ xác minh.
7. Ghi delivery semantics, idempotency, retry, retention và observability theo phạm vi áp dụng.
8. Cập nhật catalog cùng pull request khi thêm, đổi hoặc retire event.
9. Kiểm tra catalog với source code/schema trong CI nhưng để owner xác nhận semantics.
10. Dùng catalog trong contract review, migration, onboarding và incident response.

Danh mục producer biến những event rải rác trong source code thành các hợp đồng có owner và ngữ cảnh rõ ràng. Khi catalog ghi đúng nguồn phát, trigger, transaction, payload, destination và consumer, các module Spring Modulith có thể tiến hóa độc lập hơn mà vẫn giữ được khả năng khám phá, đánh giá ảnh hưởng và vận hành giao tiếp bằng application events.
