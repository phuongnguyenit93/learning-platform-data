# Event catalog cho ứng dụng Spring Modulith

Khi một ứng dụng có nhiều module phát và nhận application event, tên event và payload rất dễ trở thành những hợp đồng ngầm. Một module đổi trường dữ liệu, một listener mới được thêm hoặc một event được externalize ra broker có thể ảnh hưởng tới nhiều consumer mà publisher không biết. **Event catalog** là danh mục có cấu trúc mô tả các event được công bố, ý nghĩa nghiệp vụ, module sở hữu, schema, cách giao nhận, consumer và vòng đời của từng hợp đồng.

Trong `SPRING_MODULITH_APPLICATION_EVENTS`, catalog giúp nhóm phát triển hiểu module nào phát event, module nào lắng nghe, event được xử lý sau commit hay được chuyển ra broker, và cách retry/quan sát khi publication chưa hoàn tất. Catalog là tài liệu hợp đồng và điểm tra cứu cho con người, review kiến trúc và quy trình thay đổi. Nó bổ sung cho code, schema registry và Event Publication Registry; không thay thế các cơ chế thực thi đó.

## 1. Vì sao cần event catalog?

Trong một hệ thống nhỏ, người phát triển có thể tìm kiếm `publishEvent()` và `@EventListener` để lần theo luồng. Khi số module và consumer tăng lên, cách này khó trả lời nhanh các câu hỏi:

- Event nào là hợp đồng được phép dùng giữa các module?
- Module nào chịu trách nhiệm về ý nghĩa và schema của event?
- Consumer nào đang phụ thuộc vào event đó?
- Event được xử lý đồng bộ, sau commit hay bất đồng bộ?
- Event có được externalize tới Kafka, RabbitMQ hoặc hệ thống khác không?
- Trường nào bắt buộc, trường nào có thể thiếu và schema version hiện tại là bao nhiêu?
- Khi đổi event, consumer cũ có tiếp tục đọc được không?
- Nếu listener lỗi, publication được retry, cách ly hay cần can thiệp thủ công?
- Ai cần được thông báo trước khi event bị deprecate hoặc ngừng phát?

Event catalog tập hợp các thông tin này thành một nơi có cấu trúc. Nhờ đó, nhóm phát triển có thể đánh giá ảnh hưởng trước khi thay đổi, onboarding consumer mới và điều tra sự cố mà không phải suy luận toàn bộ hợp đồng từ implementation.

## 2. Phân biệt event catalog với các loại tài liệu khác

Event catalog có liên hệ với nhiều artifact nhưng mỗi loại phục vụ một mục đích riêng:

| Artifact | Trả lời câu hỏi | Vai trò |
| --- | --- | --- |
| Event catalog | Hệ thống có những event nào, ai sở hữu và ai sử dụng? | Danh mục tổng hợp và tra cứu hợp đồng |
| Event schema | Payload của một event có cấu trúc và kiểu dữ liệu gì? | Hợp đồng máy đọc được hoặc mô tả chi tiết payload |
| AsyncAPI/API documentation | Producer, channel, message và protocol kết nối ra sao? | Mô tả giao diện tích hợp bất đồng bộ |
| Source code | Event được tạo và xử lý bằng implementation nào? | Hiện thực publisher, listener và adapter |
| Event Publication Registry | Publication tới listener đã hoàn tất hay còn dang dở? | Theo dõi giao event ở runtime và hỗ trợ phục hồi |
| Event store | Lịch sử event nào được lưu và có thể replay? | Nguồn dữ liệu lịch sử nếu hệ thống triển khai event sourcing hoặc lưu event riêng |

Catalog không phải một bản sao của toàn bộ source code. Nó ghi lại thông tin cần để sử dụng và quản lý hợp đồng. Schema có thể được đặt ở một kho riêng rồi liên kết từ catalog; code vẫn là nơi thực thi hành vi.

Đặc biệt, Event Publication Registry không phải event catalog và cũng không mặc định là event store. Registry theo dõi publication theo listener được cấu hình; catalog mô tả hợp đồng ở cấp thiết kế; event store lưu lịch sử nghiệp vụ nếu ứng dụng có triển khai cơ chế đó.

## 3. Những loại event nên có trong catalog

Không phải mọi object được truyền qua một phương thức nội bộ đều cần trở thành entry trong catalog. Nên ưu tiên event có ý nghĩa tại ranh giới module hoặc ranh giới tích hợp.

| Loại event | Ví dụ | Có nên catalog? |
| --- | --- | --- |
| Domain event được module công bố | `OrderCompleted`, `PaymentAuthorized` | Có, nếu module khác được phép phụ thuộc vào hợp đồng này |
| Integration event externalize | `CustomerProfileChanged` gửi tới broker | Có, luôn cần mô tả destination và schema |
| Event nội bộ chỉ phục vụ implementation | `RecalculateTemporaryTotal` | Thường không cần catalog công khai |
| Event kỹ thuật/quan sát | `ProjectionRebuilt`, `ConsumerLagDetected` | Có thể catalog nếu có consumer hoặc quy trình vận hành phụ thuộc |
| Event thử nghiệm/test fixture | `FakeOrderCompleted` | Không đưa vào catalog production |

Một event nội bộ vẫn có thể cần tài liệu nếu nó là hợp đồng ổn định giữa các module. Ngược lại, một class có hậu tố `Event` nhưng chỉ dùng trong một class hoặc một package không tự động trở thành public event contract.

## 4. Cấu trúc thông tin của một catalog entry

Một entry nên đủ ngắn để tra cứu nhưng đủ chi tiết để consumer hiểu cách sử dụng. Các nhóm metadata thường hữu ích:

| Nhóm | Trường gợi ý | Mục đích |
| --- | --- | --- |
| Identity | Event name, event type, stable ID | Nhận diện hợp đồng |
| Ownership | Owning module, owner team/contact | Xác định nơi thay đổi và nơi hỏi khi có vấn đề |
| Meaning | Business purpose, trigger, semantic guarantees | Giải thích event biểu thị điều gì |
| Schema | Schema version, schema reference, required/optional fields | Đọc và tiến hóa payload |
| Producer | Publisher module, transaction boundary, publish condition | Biết khi nào event được phát |
| Delivery | Internal/external, channel, exchange/topic, routing key | Biết event được giao qua đâu |
| Consumers | Consumer module/service, purpose, criticality | Đánh giá blast radius |
| Ordering | Aggregate/partition key, sequence/version | Hiểu thứ tự được bảo đảm |
| Reliability | Delivery semantics, retry, idempotency, DLQ | Biết cách xử lý duplicate và lỗi |
| Security | Data classification, PII, authorization | Kiểm soát dữ liệu và quyền truy cập |
| Lifecycle | Status, introduced/deprecated dates, replacement | Quản lý thay đổi và ngừng sử dụng |
| Operations | Metrics, dashboard, runbook, SLO | Hỗ trợ vận hành |

Không nhất thiết mọi event đều cần tất cả trường. Trường không áp dụng nên ghi rõ `not applicable` hoặc bỏ theo quy ước của catalog; tránh để trống khiến người đọc không biết thông tin chưa được xác định hay thực sự không cần.

## 5. Quy tắc đặt tên event

Tên event nên mô tả một điều đã xảy ra, thường dùng dạng quá khứ hoặc trạng thái đã hoàn tất:

- `OrderPlaced`
- `OrderCompleted`
- `PaymentAuthorized`
- `InventoryReserved`
- `ShipmentDispatched`
- `CustomerProfileChanged`

Tên như `PlaceOrder`, `ReserveInventory` hoặc `SendPayment` thường biểu thị command/yêu cầu thực hiện hành động. Event nên mô tả kết quả hoặc sự kiện đã xảy ra. Phân biệt command với event giúp consumer không hiểu nhầm một yêu cầu là kết quả chắc chắn đã thành công.

Tên cần ổn định và không phụ thuộc implementation. Tránh đưa tên class private, tên package nội bộ hoặc tên bảng database vào hợp đồng nếu chúng không mang ý nghĩa nghiệp vụ. Với event externalize, routing key nên phản ánh loại event hoặc bounded context, ví dụ `order.completed`, thay vì tên người dùng, email hoặc ID của đối tượng.

## 6. Ví dụ catalog cho một event

Giả sử module `orders` phát `OrderCompleted` khi đơn hàng chuyển sang trạng thái hoàn tất. Module `billing` tạo chứng từ, module `analytics` cập nhật số liệu và module `notifications` gửi thông báo.

Một entry có thể được biểu diễn như sau:

```yaml
id: orders.order-completed
name: OrderCompleted
eventType: com.example.orders.OrderCompleted
menuVersion: 1
status: active

ownership:
  module: orders
  team: commerce-platform

meaning:
  summary: Đơn hàng đã hoàn tất theo quy tắc nghiệp vụ của module orders.
  trigger: Transaction hoàn tất đơn hàng đã commit thành công.
  guarantees:
    - Chỉ phát sau khi trạng thái đơn hàng được commit.
    - orderId xác định aggregate phát sinh event.

schema:
  version: 1
  format: Java record / JSON
  required:
    - eventId
    - orderId
    - completedAt
  optional:
    - customerReference
  compatibility: backward-compatible additions only

producer:
  module: orders
  transactionPhase: AFTER_COMMIT

delivery:
  kind: externalized
  exchange: orders.events
  routingKey: order.completed

consumers:
  - name: billing
    purpose: Tạo chứng từ cho đơn hàng hoàn tất.
    criticality: high
  - name: analytics
    purpose: Cập nhật read model phân tích.
    criticality: medium
  - name: notifications
    purpose: Lên lịch thông báo hoàn tất đơn hàng.
    criticality: medium

reliability:
  delivery: at-least-once
  idempotencyKey: eventId per consumer
  ordering: per order aggregate

security:
  classification: internal
  personalData: customerReference is pseudonymous

lifecycle:
  introduced: 1.0
  deprecated: false

operations:
  dashboard: Order event delivery
  runbook: OrderCompleted publication recovery
```

Đây là định dạng minh họa do tổ chức tự quy ước, không phải schema mặc định của Spring Modulith. Tên field, cách lưu catalog và validation cần được thống nhất trong dự án. Không ghi `delivery: at-least-once` hoặc `AFTER_COMMIT` nếu implementation và cấu hình thực tế chưa bảo đảm các semantics đó.

## 7. Mô tả publisher và điều kiện phát event

Catalog nên cho biết event được phát bởi module nào và điều kiện nghiệp vụ nào làm event xuất hiện. Thông tin này giúp consumer hiểu event có nghĩa gì và tránh phụ thuộc vào thời điểm implementation ngẫu nhiên.

Ví dụ publisher:

```java
@Service
class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events
    ) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void complete(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.complete();

        events.publishEvent(new OrderCompleted(
                UUID.randomUUID(),
                order.getId(),
                Instant.now()
        ));
    }
}
```

Trong ví dụ, publisher gọi `publishEvent()` trong transaction. Nếu event được xử lý bằng listener transaction-bound sau commit, catalog cần mô tả phase tương ứng. Không được chỉ nhìn vị trí `publishEvent()` rồi kết luận listener luôn chạy sau commit; semantics còn phụ thuộc loại listener và cấu hình.

Nên ghi rõ các trường hợp event không được phát. Ví dụ, nếu transaction hoàn tất đơn hàng rollback, listener `AFTER_COMMIT` không nên thực hiện side effect. Nếu publisher phát event cho trạng thái trung gian, catalog phải phân biệt rõ với `OrderCompleted`.

## 8. Mô tả consumer và trách nhiệm xử lý

Mỗi consumer cần được ghi kèm mục đích và trách nhiệm dữ liệu. Không chỉ liệt kê tên class listener; tên module hoặc service thường ổn định hơn tên implementation.

Ví dụ:

| Consumer | Mục đích | Dữ liệu sở hữu được cập nhật | Mức quan trọng |
| --- | --- | --- | --- |
| `billing` | Tạo chứng từ | Invoice record | Cao |
| `analytics` | Cập nhật báo cáo | Analytics projection | Trung bình |
| `notifications` | Gửi thông báo | Notification request/outbox | Trung bình |

Catalog nên ghi rõ consumer có xử lý event đồng bộ hay bất đồng bộ, có transaction riêng hay không và có thể retry ra sao. Nếu consumer gọi hệ thống ngoài, cần nêu idempotency key hoặc business operation key để tránh side effect trùng.

Consumer không nên tự ý đọc database nội bộ của producer. Nếu cần dữ liệu bổ sung, catalog nên chỉ tới public API hoặc hợp đồng khác do module sở hữu dữ liệu công bố.

## 9. Phân biệt event nội bộ và event externalized

Spring Modulith hỗ trợ event nội bộ qua Spring application event mechanism. Event được đánh dấu `@Externalized` có thể được chuyển tới externalization adapter như AMQP hoặc Kafka tùy dependency và cấu hình ứng dụng.

Ví dụ:

```java
@Externalized("orders.events::order.completed")
public record OrderCompleted(
        UUID eventId,
        UUID orderId,
        Instant completedAt
) {}
```

Với AMQP integration, target trong cấu hình externalization có thể xác định exchange và phần sau `::` xác định routing key theo adapter. Với Kafka, mapping đích và key phụ thuộc adapter/cấu hình tương ứng. Catalog phải ghi đúng channel thực tế của từng adapter; không suy luận một cú pháp cho mọi broker.

| Thuộc tính | Internal event | Externalized event |
| --- | --- | --- |
| Phạm vi | Listener trong application context | Broker hoặc hệ thống ngoài |
| Hợp đồng | Có thể dùng Java type nội bộ nếu không công bố ra ngoài | Nên có schema/hợp đồng ổn định, độc lập implementation |
| Serialization | Không nhất thiết serialize qua broker | Cần serializer/message converter và schema tương thích |
| Consumer | Module listener trong ứng dụng | Consumer nội bộ qua adapter hoặc ứng dụng độc lập |
| Catalog | Ghi module phát/nhận và transaction semantics | Bổ sung destination, routing/key, schema, security và retention |

Một event có thể vừa được listener nội bộ xử lý vừa được externalize. Khi đó, catalog cần mô tả từng đường giao nhận riêng vì retry, trạng thái và người vận hành có thể khác nhau.

## 10. Schema và quy tắc versioning

Catalog cần chỉ ra schema version hiện tại và nơi lưu schema chi tiết. Không nên ghi toàn bộ schema dài vào mỗi entry nếu dự án đã có schema registry hoặc thư mục schema riêng; hãy dùng liên kết hoặc định danh có version.

Ví dụ payload:

```java
public record OrderCompletedV1(
        UUID eventId,
        UUID orderId,
        Instant completedAt
) {}
```

Khi thêm trường optional:

```java
public record OrderCompletedV2(
        UUID eventId,
        UUID orderId,
        Instant completedAt,
        String customerReference
) {}
```

Việc thêm trường chỉ an toàn nếu serializer, schema policy và consumer cũ xử lý được payload mới. Trường bắt buộc mới, thay đổi kiểu hoặc thay đổi ý nghĩa có thể là breaking change. Catalog nên ghi:

- Schema version hiện tại.
- Phiên bản đầu tiên giới thiệu event.
- Trường required/optional và quy tắc null.
- Quy tắc tương thích được chọn.
- Consumer còn sử dụng schema cũ.
- Kế hoạch deprecation và ngày ngừng hỗ trợ nếu có.

Không dùng phiên bản ứng dụng producer thay cho schema version. Một release ứng dụng có thể phát nhiều event schema khác nhau.

## 11. Thứ tự, duplicate và delivery semantics

Consumer cần biết event có thể được giao lặp và thứ tự được bảo đảm ở phạm vi nào. Catalog nên mô tả các bảo đảm đã được xác nhận:

- Event có `eventId` ổn định để nhận diện lần phát cụ thể.
- Event có aggregate ID và version/sequence nếu cần thứ tự theo aggregate.
- Delivery có thể là at-most-once, at-least-once hoặc semantics khác theo cấu hình thật.
- Consumer cần idempotent khi có redelivery/retry.
- Retry policy, dead-letter/quarantine và cách xử lý poison event.
- Thời gian retention và khả năng replay nếu nguồn hỗ trợ.

Không tuyên bố exactly-once end-to-end chỉ vì broker hoặc registry có một cơ chế xác nhận. Database, broker và side effect ngoài thường không cùng một transaction. Nếu consumer commit dữ liệu rồi dừng trước acknowledgement, event có thể được giao lại; idempotency vẫn cần thiết.

## 12. Transaction phase và Event Publication Registry

Catalog nên ghi rõ listener được kích hoạt theo transaction phase nào. Ví dụ `AFTER_COMMIT` có nghĩa listener chỉ xử lý sau khi transaction nguồn commit thành công theo cấu hình. Nếu listener cần ghi dữ liệu, nó thường cần transaction xử lý riêng.

Event Publication Registry theo dõi publication tới transactional listener và cho phép quan sát/phục hồi publication chưa hoàn tất theo API được hỗ trợ. Catalog có thể liên kết event với dashboard hoặc runbook dùng registry để:

- Theo dõi số publication chưa hoàn tất theo listener.
- Xem tuổi publication lâu nhất.
- Điều tra exception và nguyên nhân listener thất bại.
- Resubmit publication sau khi khắc phục nguyên nhân.

Catalog không nên ghi trạng thái runtime hiện tại như một giá trị cố định trong hợp đồng. `active` hoặc `deprecated` mô tả vòng đời event; publication `COMPLETED` hay `INCOMPLETE` là trạng thái runtime của từng lần giao.

## 13. Phân loại dữ liệu và bảo mật

Mỗi entry nên chỉ rõ event có dữ liệu cá nhân hoặc dữ liệu nhạy cảm không. Catalog giúp consumer biết trường nào được phép sử dụng và mục đích nào được chấp nhận.

Một số thông tin cần ghi:

- Phân loại dữ liệu: public, internal, confidential hoặc phân loại của tổ chức.
- Trường có PII hoặc định danh giả danh.
- Consumer nào được phép đọc.
- Có cần tokenization, masking hoặc mã hóa trường không.
- Quyền publish/consume và chính sách broker ACL.
- Retention của publication registry, queue, DLQ, log và backup.
- Link tới hướng dẫn xử lý dữ liệu cá nhân nếu có.

Không đưa email, số điện thoại, access token hoặc payload thật vào catalog. Catalog mô tả loại dữ liệu và quy tắc bảo vệ, không phải nơi lưu dữ liệu production.

## 14. Ownership và trách nhiệm thay đổi

Mỗi event cần có một module sở hữu ý nghĩa nghiệp vụ và schema. Consumer có thể đề xuất thay đổi, nhưng owner của event chịu trách nhiệm đánh giá và công bố hợp đồng.

Ownership nên bao gồm:

- Module sở hữu event.
- Nhóm chịu trách nhiệm hoặc kênh liên hệ nội bộ.
- Người/nhóm review schema change.
- Nhóm consumer cần được thông báo trước breaking change.
- Nơi lưu schema, tài liệu và runbook.
- Cách xử lý khi owner hoặc team thay đổi.

Không để một event có nhiều owner ngang nhau mà không có người chịu trách nhiệm cuối cùng. Với event liên module, module phát event thường sở hữu ý nghĩa và schema; consumer sở hữu logic xử lý và dữ liệu đích của mình.

## 15. Vòng đời event trong catalog

Một event contract thường đi qua các trạng thái:

```text
Proposed -> Active -> Deprecated -> Retired
                  \-> Replaced by a new event
```

| Trạng thái | Ý nghĩa | Yêu cầu quản lý |
| --- | --- | --- |
| Proposed | Đang được thiết kế/review | Chưa được xem là hợp đồng production |
| Active | Được phép phát và sử dụng | Schema, owner và consumer đã được công bố |
| Deprecated | Không khuyến nghị consumer mới; đang chuyển đổi | Có replacement, thời hạn và kế hoạch migration |
| Retired | Không còn được phát hoặc hỗ trợ | Consumer đã di chuyển; có chính sách dữ liệu lịch sử |

Deprecation không có nghĩa xóa event ngay lập tức. Cần kiểm tra mọi consumer đang hoạt động, backlog, replay window và payload lịch sử trước khi ngừng hỗ trợ. Nếu có event thay thế, catalog cần liên kết entry cũ với entry mới và mô tả mapping.

## 16. Tổ chức catalog để dễ tra cứu

Catalog có thể được tổ chức theo module sở hữu, domain hoặc event type. Với ứng dụng Spring Modulith, nhóm theo module thường giúp người phát triển tìm đúng owner nhanh hơn.

Ví dụ chỉ mục:

| Module sở hữu | Event | Consumer chính | Kênh |
| --- | --- | --- | --- |
| `orders` | `OrderPlaced` | `inventory`, `notifications` | Internal + `orders.events` |
| `orders` | `OrderCompleted` | `billing`, `analytics`, `shipping` | `orders.events` |
| `payments` | `PaymentAuthorized` | `orders`, `analytics` | Internal + `payments.events` |
| `inventory` | `InventoryReserved` | `orders`, `shipping` | Internal |

Một event có thể có nhiều channel hoặc nhiều consumer. Catalog cần tránh sao chép các entry mâu thuẫn cho cùng một hợp đồng. Có thể dùng một entry chuẩn và các liên kết từ module consumer.

Đối với số lượng event lớn, nên có thể lọc theo owner, domain, consumer, event type, schema version, lifecycle status và data classification. Tìm kiếm theo tên event chỉ là một phần; tìm theo consumer giúp đánh giá blast radius khi thay đổi.

## 17. Kiểm tra tính đầy đủ của catalog

Catalog cần được duy trì cùng code và schema. Có thể bổ sung kiểm tra tự động để phát hiện event được externalize nhưng chưa có entry, consumer đã xóa nhưng catalog còn active, hoặc schema version trong code không khớp tài liệu.

Một checklist review entry:

- [ ] Event name và event type ổn định, có ý nghĩa nghiệp vụ.
- [ ] Module owner và nhóm chịu trách nhiệm được xác định.
- [ ] Trigger và điều kiện publish được mô tả rõ.
- [ ] Required/optional fields và schema version được ghi.
- [ ] Transaction phase và sync/async semantics được xác nhận.
- [ ] Internal/external delivery và destination được mô tả chính xác.
- [ ] Consumers và mục đích sử dụng được liệt kê.
- [ ] Ordering, duplicate, idempotency và retry được nêu.
- [ ] Data classification, PII và authorization được đánh giá.
- [ ] Retention, DLQ, dashboard và runbook được liên kết khi cần.
- [ ] Lifecycle status và replacement/deprecation plan được cập nhật.

Không nên biến catalog thành một biểu mẫu bắt buộc quá lớn cho mọi event nội bộ nhỏ. Hãy áp dụng mức chi tiết theo mức độ công khai, số lượng consumer và rủi ro nghiệp vụ.

## 18. Tích hợp catalog vào quy trình phát triển

Để catalog không trở thành tài liệu lỗi thời, cần đưa cập nhật vào quy trình thay đổi event:

1. Khi thêm event mới, tạo entry trước hoặc cùng thay đổi code.
2. Khi thay schema, cập nhật version và đánh giá consumer hiện tại.
3. Khi thêm consumer, cập nhật danh sách consumer và mục đích sử dụng.
4. Khi externalize event, bổ sung channel, destination, routing/key và security.
5. Khi thay đổi transaction phase hoặc retry policy, cập nhật delivery semantics.
6. Khi deprecate event, ghi replacement, thời hạn và migration plan.
7. Trong pull request, review code, schema và catalog cùng nhau.
8. Trong release, xác nhận catalog phản ánh đúng phiên bản event đang được triển khai.

Có thể dùng contract test hoặc schema compatibility check trong CI để kiểm tra schema. Có thể dùng script hoặc build check riêng để phát hiện externalized event chưa được catalog hóa. Các kiểm tra đó cần dựa trên public API và quy ước thực tế của dự án, không nên phân tích source code bằng regex đơn giản rồi coi kết quả là đầy đủ.

## 19. Ví dụ thay đổi event có ảnh hưởng consumer

Giả sử `OrderCompleted` version 1 chỉ có `eventId`, `orderId` và `completedAt`. Nhóm muốn thêm `customerReference` để consumer analytics liên kết dữ liệu.

Trước khi phát version mới, owner cần:

1. Xác nhận trường mới có thực sự cần thiết và không chứa dữ liệu cá nhân trực tiếp.
2. Đánh dấu optional nếu consumer cũ phải tiếp tục đọc payload.
3. Kiểm tra serializer và schema compatibility policy.
4. Liệt kê consumer hiện tại và kiểm tra consumer có bỏ qua unknown field hay không.
5. Cập nhật schema version/catalog entry và fixture.
6. Triển khai producer/consumer theo thứ tự tương thích.
7. Quan sát lỗi deserialize và publication incomplete sau rollout.

Nếu thay đổi làm đổi ý nghĩa `completedAt`, ví dụ từ thời điểm nghiệp vụ hoàn tất sang thời điểm hệ thống ghi nhận, chỉ thêm một version number chưa đủ. Cần định nghĩa rõ semantics mới, có thể thêm trường riêng hoặc event type mới.

## 20. Quan sát và runbook trong catalog

Catalog nên giúp người vận hành tìm từ event tới tín hiệu runtime. Với event quan trọng, có thể liên kết:

- Dashboard publication registry và tuổi publication.
- Metrics listener/consumer, queue depth và consumer lag.
- Log/trace query theo event type hoặc correlation ID.
- Runbook xử lý publication incomplete, broker outage hoặc poison event.
- Hướng dẫn resubmit và điều kiện an toàn trước khi retry.
- SLO xử lý event và mức độ ảnh hưởng nghiệp vụ.

Không đưa event ID cụ thể hoặc dữ liệu khách hàng vào entry tĩnh. Catalog liên kết tới dashboard và runbook; định danh từng lần xử lý được tra cứu trong hệ thống observability theo quyền truy cập.

Runbook cần nêu rõ không xóa publication incomplete để làm sạch dashboard và không đánh dấu hoàn tất bằng cách sửa database nếu side effect chưa được xác nhận. Retry phải xét idempotency và trạng thái hệ thống ngoài.

## 21. Những lỗi thường gặp khi xây dựng event catalog

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ liệt kê tên event | Không biết owner, consumer và ý nghĩa | Ghi purpose, producer, consumer và lifecycle |
| Coi mọi class có chữ `Event` là public contract | Catalog chứa implementation detail và nhiễu | Chỉ catalog event qua ranh giới hoặc có consumer phụ thuộc |
| Dùng producer app version làm schema version | Không xác định được payload format | Version hóa từng event contract |
| Không ghi consumer | Không đánh giá được blast radius | Liệt kê module/service và mục đích sử dụng |
| Không ghi transaction phase | Consumer hiểu sai thời điểm dữ liệu đã commit | Mô tả publish condition và listener phase |
| Coi Event Publication Registry là event store | Thiết kế replay lịch sử sai | Ghi rõ nguồn replay thực tế |
| Ghi exactly-once khi chưa chứng minh | Consumer bỏ qua idempotency và xử lý duplicate | Mô tả semantics thực tế và retry window |
| Đưa PII hoặc payload production vào catalog | Tài liệu trở thành nơi lưu dữ liệu nhạy cảm | Chỉ ghi phân loại và quy tắc bảo vệ |
| Không cập nhật catalog cùng code | Tài liệu nhanh chóng lỗi thời | Review catalog trong cùng thay đổi schema/code |
| Deprecate mà không rà consumer | Consumer đang hoạt động bị phá vỡ | Có inventory, replacement và migration window |

## 22. Quy trình tạo và duy trì event catalog

Khi thêm hoặc thay đổi một application event, hãy thực hiện theo thứ tự:

1. Xác định event có phải hợp đồng tại ranh giới module hoặc tích hợp không.
2. Xác định module sở hữu ý nghĩa nghiệp vụ và schema.
3. Mô tả event name, trigger, payload và schema version.
4. Ghi publisher, transaction phase và internal/external delivery.
5. Liệt kê consumer, mục đích và dữ liệu mà mỗi consumer cập nhật.
6. Ghi ordering, duplicate, idempotency, retry và dead-letter policy.
7. Đánh giá data classification, PII, authorization và retention.
8. Gắn dashboard, metrics và runbook cho luồng quan trọng.
9. Cập nhật lifecycle status và replacement khi deprecate.
10. Review catalog cùng code/schema và kiểm tra compatibility trước release.

Event catalog tạo ra cái nhìn thống nhất về các hợp đồng sự kiện trong ứng dụng. Khi mỗi event có owner, ý nghĩa, schema, consumer, delivery semantics và vòng đời rõ ràng, nhóm phát triển có thể mở rộng publisher/listener, thêm consumer và thay đổi payload có kiểm soát. Catalog cũng giúp vận hành lần theo publication, retry và tác động của một event mà vẫn giữ được ranh giới module của Spring Modulith.
