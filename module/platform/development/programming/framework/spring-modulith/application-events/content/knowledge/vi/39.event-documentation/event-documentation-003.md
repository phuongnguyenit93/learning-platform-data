# Danh mục consumer

Trong hệ thống hướng sự kiện, một event có thể được nhiều listener trong ứng dụng hoặc nhiều dịch vụ bên ngoài tiêu thụ. Khi số lượng module, topic và consumer tăng, nhóm phát triển cần biết ai đang nhận event nào, nhận qua cơ chế gì, xử lý với contract phiên bản nào và ai chịu trách nhiệm khi có lỗi. **Danh mục consumer** là bản kiểm kê có cấu trúc về các subscriber của event, giúp quản lý dependency, thay đổi contract, vận hành và điều tra sự cố.

Danh mục này cần bao quát cả consumer nội bộ Spring Modulith lẫn consumer qua broker như Kafka. Một listener trong cùng ứng dụng có thể được định danh bằng module và bean/method; consumer bên ngoài thường được định danh bằng service, topic và consumer group. Hai loại có cách triển khai khác nhau nhưng đều cần owner, mục đích, contract, delivery semantics và vòng đời rõ ràng.

## 1. Vì sao cần danh mục consumer?

Khi một producer thay đổi event, câu hỏi đầu tiên thường là những ai đang sử dụng event đó. Nếu không có inventory, nhóm phát triển có thể chỉ biết các consumer đang hoạt động trong môi trường hiện tại mà bỏ sót batch job chạy hàng tháng, replay worker, data pipeline hoặc ứng dụng đối tác đang tạm ngừng.

Danh mục consumer giúp:

- Xác định tác động trước khi đổi event schema hoặc ngừng một trường.
- Biết module hoặc dịch vụ nào phụ thuộc vào event.
- Tìm owner chịu trách nhiệm xử lý lỗi và xác nhận thay đổi.
- Kiểm soát consumer group, topic, partition và quyền truy cập.
- Đánh giá version compatibility và kế hoạch rollout.
- Theo dõi retry, dead-letter, lag và SLA xử lý.
- Nhận diện consumer cũ, trùng lặp hoặc không còn được sử dụng.
- Hỗ trợ replay, migration và kiểm toán dữ liệu.

Danh mục không chỉ là danh sách topic. Một topic có thể được nhiều consumer group đọc độc lập; một consumer logic có thể đọc nhiều topic; một module có thể có nhiều listener cho cùng event. Vì vậy, cần ghi rõ quan hệ giữa event, subscription và consumer thay vì gộp tất cả thành một dòng tên topic.

## 2. Phân biệt producer, event, subscription và consumer

Các thực thể sau cần được phân biệt:

| Thực thể | Ý nghĩa | Ví dụ |
|---|---|---|
| Producer | Thành phần phát event | Module Orders |
| Event contract | Hợp đồng dữ liệu và ý nghĩa nghiệp vụ | OrderPaid v2 |
| Destination | Nơi event được công bố | Logical target hoặc Kafka topic |
| Subscription | Quan hệ đăng ký nhận một event/destination | Listener OrdersProjection nhận OrderPaid |
| Consumer | Thành phần thực hiện xử lý | Bean listener hoặc service Inventory |
| Consumer group | Nhóm instance cùng chia tải một subscription Kafka | inventory-projection |
| Owner | Nhóm hoặc vai trò chịu trách nhiệm | Team Inventory |

Trong Spring Modulith, consumer nội bộ có thể là method được đánh dấu bằng @ApplicationModuleListener hoặc listener phù hợp khác. Publication được theo dõi theo listener, vì vậy hai listener khác nhau trong cùng module có thể là hai subscriber độc lập.

Với Kafka, consumer group biểu diễn một subscription logic có các instance chia partition. Các instance trong cùng group thường không nhận mỗi record một lần cho từng instance; chúng chia nhau công việc. Hai group khác nhau có thể đọc độc lập cùng một topic.

Không coi tên class event, logical target, topic và consumer group là cùng một định danh. Chúng nằm ở các lớp khác nhau và có vòng đời khác nhau.

## 3. Phạm vi cần kiểm kê

Một danh mục đầy đủ nên bao gồm các loại consumer sau:

- Listener nội bộ trong cùng ứng dụng Spring Modulith.
- Consumer service đọc Kafka hoặc broker khác.
- Worker xử lý event từ inbox hoặc database staging.
- Batch job, scheduled job và replay tool đọc event lịch sử.
- Data warehouse, analytics pipeline và search indexer.
- Adapter tích hợp với hệ thống đối tác.
- Consumer tạm thời phục vụ migration, backfill hoặc reconciliation.
- Consumer vận hành như audit, notification hoặc monitoring.

Không chỉ kiểm kê consumer đang chạy. Một job theo lịch có thể không xuất hiện trong telemetry nhiều tuần nhưng vẫn là subscriber hợp lệ. Hãy kết hợp source code, cấu hình triển khai, topic ACL, schema registry, tài liệu tích hợp và xác nhận của owner.

Cần ghi rõ trạng thái consumer: planned, active, deprecated, paused hoặc retired. Một consumer paused vẫn có thể cần đọc lại dữ liệu khi được bật lại; trạng thái này ảnh hưởng tới retention và replay plan.

## 4. Các trường thông tin tối thiểu

Mỗi consumer nên có một bản ghi với các trường sau:

| Nhóm | Trường | Mục đích |
|---|---|---|
| Identity | Consumer ID | Định danh ổn định trong catalog |
| Identity | Name | Tên dễ đọc của subscriber |
| Ownership | Owner team/contact | Nhóm chịu trách nhiệm |
| Ownership | Business purpose | Lý do consumer cần event |
| Source | Producer/module | Module phát event |
| Contract | Event type và version | Loại event, schema/contract version hỗ trợ |
| Subscription | Logical target/topic | Destination mà consumer đọc |
| Subscription | Consumer group | Group ID nếu dùng broker |
| Implementation | Module/service và handler | Vị trí code thực hiện xử lý |
| Processing | Delivery semantics | At-least-once, retry, idempotency |
| Processing | Ordering/key | Khóa hoặc sequence cần giữ thứ tự |
| Operations | Retry/DLT policy | Cách xử lý lỗi và event poison |
| Operations | SLA/lag target | Thời gian xử lý và ngưỡng backlog |
| Security | Data classification/access | Phân loại dữ liệu và quyền đọc |
| Lifecycle | Status/deprecation date | Trạng thái và kế hoạch ngừng |
| Governance | Last reviewed | Thời điểm owner xác nhận gần nhất |

Không phải trường nào cũng áp dụng cho mọi consumer. Ví dụ listener nội bộ không có Kafka group ID; consumer đọc topic compacted có thể cần ghi rõ semantics tombstone. Nên giữ schema catalog thống nhất nhưng cho phép trường không áp dụng được để trống kèm lý do.

## 5. Định danh consumer ổn định

Consumer ID cần ổn định qua lần deploy và không phụ thuộc instance ID hoặc pod name. Instance có thể được tạo/xóa tự động; catalog mô tả subscription logic.

Ví dụ:

~~~text
orders.order-summary-listener
inventory.stock-reservation-consumer
analytics.order-events-sink
operations.event-replay-worker
~~~

Nếu một service có hai subscription độc lập với policy hoặc owner khác nhau, hãy tạo hai consumer ID. Nếu nhiều instance cùng group chỉ chia tải một subscription, thường ghi một consumer entry với group ID và số instance là thông tin runtime.

Không dùng tên người cụ thể làm owner lâu dài. Ghi team hoặc vai trò chịu trách nhiệm và một kênh liên hệ vận hành được quản lý. Khi nhân sự thay đổi, ownership của consumer không nên biến mất.

## 6. Lập danh mục consumer nội bộ Spring Modulith

Với consumer nội bộ, ghi nhận module sở hữu handler, event type, listener method và semantics xử lý. Ví dụ:

~~~java
package com.example.inventory;

@Component
class StockProjectionListener {

    @ApplicationModuleListener
    void on(StockReserved event) {
        // Cập nhật read model của Inventory.
    }
}
~~~

Một dòng catalog tương ứng có thể chứa:

- Consumer ID: inventory.stock-projection.
- Consumer kind: modulith-listener.
- Producer module: inventory hoặc module phát event thực tế.
- Event type: StockReserved.
- Handler: StockProjectionListener#on.
- Transaction behavior: xử lý theo semantics của ApplicationModuleListener và cấu hình hiện tại.
- Idempotency: event ID hoặc aggregate version được dùng để chống xử lý lặp.
- Owner: team sở hữu module Inventory.

Không suy luận producer module từ package của consumer. Ghi đúng module phát event theo contract. Nếu một event được phát từ module khác, đó là dependency cần được phản ánh trong catalog.

Spring Modulith Event Publication Registry theo dõi publication tới từng listener. Khi một event có nhiều listener, mỗi publication cần được điều tra theo subscriber tương ứng. Danh mục consumer giúp ánh xạ listener ID/handler tới owner và mục đích nghiệp vụ.

## 7. Lập danh mục consumer qua Kafka

Với consumer bên ngoài, cần ghi thêm các thông tin transport:

- Kafka cluster hoặc môi trường áp dụng.
- Topic vật lý và event type/schema version.
- Consumer group ID.
- Service và deployment owner.
- Partition assignment/concurrency dự kiến.
- Key strategy và ordering requirement.
- Deserializer/schema registry subject.
- Offset/acknowledgment policy.
- Retry topic hoặc dead-letter topic.
- ACL principal và quyền đọc topic/group.

Ví dụ một consumer group có thể có nhiều instance để chia partition. Catalog mô tả group như một subscription logic và có thể liên kết tới deployment/service quản lý các instance.

Nếu một service đọc nhiều topic trong cùng group, ghi từng topic subscription hoặc dùng một consumer entry có danh sách destination rõ ràng. Không chỉ ghi group ID mà bỏ qua topic vì group có thể subscribe nhiều luồng với contract khác nhau.

## 8. Ví dụ catalog dạng YAML

Một bản ghi có cấu trúc có thể được biểu diễn như sau:

~~~yaml
consumerId: inventory.stock-projection
name: Stock projection listener
kind: modulith-listener
status: active

ownership:
  team: inventory-platform
  contact: "#inventory-oncall"
  purpose: Cập nhật read model tồn kho sau khi reservation được xác nhận

subscription:
  producerModule: inventory
  eventType: StockReserved
  contractVersion: 1
  logicalTarget: inventory.stock-reserved.v1
  topic: null
  consumerGroup: null

implementation:
  module: inventory
  handler: StockProjectionListener#on
  processingMode: after-commit

delivery:
  semantics: at-least-once
  idempotencyKey: eventId
  orderingKey: reservationId
  retryPolicy: bounded-retry
  deadLetterDestination: inventory.stock-projection.quarantine

operations:
  ownerSla: 2m
  dashboard: inventory-event-consumer
  lastReviewed: 2026-11-25
~~~

Đây là ví dụ minh họa, không phải cấu hình mà Spring Modulith tự đọc. Các field như contact, dashboard, SLA và status là metadata do tổ chức quản lý. Với listener nội bộ, topic và consumer group có thể không áp dụng; dùng null hoặc bỏ field theo schema catalog đã thống nhất.

Không lưu secret, credential hoặc payload thực trong catalog. Chỉ ghi tên secret reference hoặc hệ thống quản lý quyền nếu cần.

## 9. Liên kết consumer với event contract

Một consumer entry cần trỏ tới contract cụ thể, không chỉ ghi “đọc order events”. Nên ghi:

- Event type ổn định.
- Contract/schema version được hỗ trợ.
- Required và optional fields mà consumer sử dụng.
- Enum values hoặc unknown-value behavior.
- Ý nghĩa của timestamp, amount, currency và identifier.
- Có hỗ trợ event cũ qua upcaster hay không.
- Có thể bỏ qua field mới hay không.
- Chính sách xử lý payload không tương thích.

Nếu consumer chỉ hỗ trợ v1, catalog cần thể hiện rõ để producer biết khi nào có thể ngừng phát v1. Nếu consumer hỗ trợ v1 và v2 qua upcaster, ghi phạm vi hỗ trợ và phiên bản code đã xác nhận.

Không coi việc deserializer không ném exception là bằng chứng consumer hiểu đúng contract. Consumer có thể đọc được payload nhưng diễn giải sai đơn vị hoặc semantics. Contract tests cần kiểm tra cả ý nghĩa dữ liệu.

## 10. Delivery semantics và idempotency

Catalog nên nêu cách consumer xử lý redelivery:

| Semantics | Ý nghĩa cần ghi |
|---|---|
| At-most-once | Event có thể bị mất nếu xác nhận trước khi xử lý hoàn tất |
| At-least-once | Event có thể được giao nhiều lần; handler cần idempotent |
| Exactly-once trong phạm vi Kafka | Cần mô tả rõ transaction và phạm vi Kafka-to-Kafka; không mặc định bao gồm database ngoài |
| Manual acknowledgment | Thời điểm commit/ack được kiểm soát bởi handler hoặc container |

Ghi rõ idempotency key hoặc cơ chế deduplication. Với database consumer, có thể dùng inbox table unique theo consumer ID và event ID; với projection trạng thái, có thể dùng aggregate version guard.

Nếu event có side effect bên ngoài như gửi email, thanh toán hoặc gọi API, catalog nên nêu idempotency key ở hệ thống đích hoặc quy trình reconciliation. Không ghi “exactly once” chung chung nếu chỉ có producer idempotence hoặc consumer group offset.

## 11. Ordering, partition và concurrency

Một số consumer cần xử lý event theo thứ tự của aggregate; một số consumer chỉ cần trạng thái cuối cùng. Catalog cần ghi:

- Ordering scope: global, per aggregate, per key hoặc không yêu cầu.
- Key được dùng để định tuyến.
- Có version/sequence hay không.
- Concurrency tối đa hoặc cách phân chia partition.
- Hành vi khi nhận version gap hoặc event cũ.
- Có thể xử lý song song giữa các aggregate hay không.

Ví dụ consumer cập nhật tồn kho theo reservation ID có thể cần thứ tự trong phạm vi reservation. Consumer analytics có thể chấp nhận xử lý song song nếu phép tổng hợp idempotent.

Không suy ra ordering toàn cục từ Kafka. Kafka bảo đảm thứ tự trong một partition; nhiều partition không có một thứ tự tổng thể. Nếu catalog ghi ordering là per aggregate, cần ghi cả key strategy và điều kiện bảo đảm.

## 12. Retry, quarantine và dead-letter ownership

Mỗi consumer cần có owner cho công việc lỗi. Catalog nên ghi:

- Retryable error categories.
- Max attempts và backoff policy.
- Deadline hoặc thời gian tối đa event được chờ.
- Quarantine/DLT destination.
- Owner nhận cảnh báo.
- Runbook điều tra và replay.
- Điều kiện skip hoặc compensation nếu có.

Dead-letter topic có thể được nhiều nhóm vận hành theo dõi; ghi rõ ai chịu trách nhiệm quyết định replay, sửa dữ liệu hoặc bỏ qua. Không coi việc record đã vào DLT là hoàn tất nghiệp vụ.

Với Spring Modulith listener nội bộ, Event Publication Registry có thể giúp tìm publication incomplete và resubmit. Catalog nên ghi handler owner và quy trình phục hồi tương ứng. Registry không tự thay thế retry policy hoặc kho quarantine của ứng dụng.

## 13. Security và phân loại dữ liệu

Consumer có thể đọc dữ liệu nhạy cảm ngay cả khi chỉ sử dụng một vài trường. Catalog cần nêu:

- Data classification của event.
- Trường nhạy cảm được consumer sử dụng.
- Mục đích xử lý và căn cứ truy cập theo chính sách nội bộ.
- Kafka ACL/topic/group permission hoặc quyền truy cập nội bộ.
- Môi trường được phép tiêu thụ.
- Quy tắc masking và log redaction.
- Retention của bản sao hoặc read model do consumer tạo.

Áp dụng quyền tối thiểu: consumer chỉ được đọc topic và group cần thiết. Không cấp quyền đọc toàn bộ cluster chỉ để thuận tiện. Với listener nội bộ, kiểm soát dependency module và package boundary giúp giới hạn nơi có thể sử dụng contract.

Không đưa payload, token, customer secret hoặc dữ liệu cá nhân vào catalog. Nếu cần tham chiếu schema hoặc data dictionary, dùng link tới tài liệu được phân quyền.

## 14. Lifecycle: planned, active, deprecated và retired

Consumer catalog cần phản ánh vòng đời subscription:

| Trạng thái | Ý nghĩa | Điều kiện chuyển |
|---|---|---|
| Planned | Đã thiết kế nhưng chưa nhận event production | Owner, contract và rollout được xác định |
| Active | Đang được hỗ trợ và có thể nhận event | Đã triển khai và có monitoring |
| Paused | Tạm dừng có chủ đích | Có kế hoạch backlog, retention và resume |
| Deprecated | Đã thông báo sẽ ngừng | Có replacement hoặc migration plan |
| Retiring | Đang chuyển traffic hoặc drain backlog | Xác minh consumer mới đã nhận trách nhiệm |
| Retired | Không còn subscription hợp lệ | ACL, deployment và tài liệu đã được dọn theo policy |

Không đánh dấu retired chỉ vì không thấy consumer trong một khoảng thời gian ngắn. Một consumer theo lịch có thể chỉ chạy mỗi tháng hoặc chỉ hoạt động khi replay. Cần xác nhận owner và thời gian quan sát đủ dài.

Khi ngừng consumer, kiểm tra group lag, offset cuối, retry/DLT backlog, quyền truy cập, dashboard, alert, schema support và các tài liệu tích hợp. Nếu consumer có thể được bật lại, giữ retention hoặc archive đủ để phục hồi.

## 15. Khám phá và duy trì danh mục

Có thể tạo inventory bằng cách kết hợp nhiều nguồn:

1. Source code: tìm @ApplicationModuleListener, @EventListener, @KafkaListener và adapter consumer.
2. Configuration: topic, group ID, deserializer, retry và listener container.
3. Modulith metadata: module ownership, named interface và event contract.
4. Broker metadata: topic, consumer group, ACL và runtime lag.
5. Schema Registry: subject, schema version và compatibility.
6. Deployment metadata: service, namespace, owner và lịch chạy.
7. Runtime telemetry: consumer đang hoạt động, throughput và lag.
8. Owner review: xác nhận consumer theo lịch, replay hoặc ít khi chạy.

Không nguồn nào đơn lẻ đầy đủ. Source code có thể chứa consumer chưa deploy; broker telemetry không thấy consumer đang dừng; ACL có thể còn quyền cũ dù subscriber đã nghỉ. Đối chiếu các nguồn và đánh dấu mức xác minh của từng bản ghi.

Nên cập nhật catalog cùng pull request thay đổi event subscription. Khi thêm listener, thay topic, đổi group ID hoặc ngừng consumer, yêu cầu cập nhật owner, contract version và vận hành trong cùng thay đổi.

## 16. Phát hiện consumer không được khai báo hoặc đã lỗi thời

Một số dấu hiệu cần điều tra:

- Consumer group xuất hiện trên broker nhưng không có entry trong catalog.
- Catalog có consumer active nhưng không thấy deployment hoặc source code.
- Consumer đọc topic không thuộc event contract đã đăng ký.
- Một topic có consumer không rõ owner.
- Group lag tăng nhưng không có dashboard hoặc runbook.
- Consumer vẫn giữ ACL sau khi đã retired.
- Schema cũ còn được hỗ trợ nhưng không biết consumer nào cần nó.
- Nhiều consumer làm cùng một projection hoặc side effect mà không có lý do rõ.

Các dấu hiệu này là đầu mối, không phải kết luận tự động. Consumer có thể chạy theo lịch hoặc dùng group ID thay đổi theo môi trường. Trước khi xóa entry, thu hồi ACL hoặc ngừng topic, xác nhận với owner và kiểm tra replay window.

## 17. Dùng catalog khi thay đổi event

Trước khi đổi event schema hoặc logical target:

1. Tìm tất cả consumer đăng ký event đó.
2. Xác định owner và mức độ quan trọng của từng consumer.
3. Kiểm tra version consumer hỗ trợ và event cũ còn cần đọc.
4. Phân loại thay đổi backward/forward compatibility.
5. Lập thứ tự rollout consumer và producer.
6. Xác định dual-read, dual-write, upcasting hoặc topic versioning nếu cần.
7. Theo dõi consumer lag, error và fallback trong giai đoạn chuyển tiếp.
8. Chỉ ngừng contract cũ sau khi mọi consumer đã chuyển và owner xác nhận.

Catalog cũng giúp tìm consumer cần kiểm thử khi thay đổi producer. Nếu một consumer không thể được kiểm thử cùng repository, contract fixture hoặc integration contract test cần được duy trì ở ranh giới giữa hai hệ thống.

## 18. Mẫu review consumer entry

Khi review một consumer mới hoặc thay đổi, người review nên xác nhận:

- Consumer ID có ổn định và duy nhất không?
- Owner và mục đích nghiệp vụ có rõ không?
- Producer module, event type và contract version có chính xác không?
- Logical target/topic và consumer group có đúng không?
- Handler hoặc service implementation có được chỉ ra không?
- Delivery semantics và idempotency có mô tả không?
- Ordering/key/concurrency có phù hợp không?
- Retry, DLT/quarantine và replay có owner không?
- Data classification, ACL và retention có được xem xét không?
- SLA, dashboard, alert và runbook có sẵn không?
- Status và last reviewed có được cập nhật không?

Nếu một trường chưa biết, ghi rõ TBD cùng owner và ngày cần hoàn tất. Không để placeholder tồn tại vô thời hạn mà không có trách nhiệm xử lý.

## 19. Checklist quản trị danh mục consumer

Một consumer catalog có thể được xem là hữu ích khi:

- Bao gồm listener nội bộ, broker consumer, batch job, replay và downstream pipeline.
- Mỗi consumer có ID ổn định, owner và mục đích nghiệp vụ.
- Event contract, version và producer được liên kết chính xác.
- Topic/logical target và group ID được ghi riêng biệt.
- Delivery semantics, idempotency, ordering và retry được mô tả.
- Security, data classification và retention có thông tin.
- Lifecycle status cùng kế hoạch deprecation được duy trì.
- Source code, broker metadata và owner review được đối chiếu.
- Mọi thay đổi subscription cập nhật catalog trong cùng quy trình review.
- Có quy trình xử lý entry không owner, stale hoặc không còn hoạt động.
- Catalog có thể dùng để lập impact analysis trước migration và incident response.

Danh mục consumer là bản đồ dependency của luồng event. Khi ghi nhận đúng subscriber, owner, contract, transport và cách phục hồi, nhóm phát triển có thể biết một thay đổi event ảnh hưởng tới ai, ai cần phối hợp và nơi cần theo dõi sau rollout. Duy trì catalog cùng source code và xác nhận định kỳ giúp hệ thống Spring Modulith phát triển mà không mất dấu các consumer phụ thuộc vào event.

