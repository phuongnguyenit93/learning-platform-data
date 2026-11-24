# Phạm vi thứ tự thông điệp và xử lý sự kiện đến muộn

Trong hệ thống phân tán, message được gửi trước chưa chắc được xử lý hoặc commit trước. Một event có thể đến trễ vì retry, mạng, partition rebalance, consumer restart hoặc một nguồn dữ liệu phát lại lịch sử. Nếu ứng dụng giả định mọi event luôn đến đúng thứ tự, trạng thái nghiệp vụ có thể bị lùi, ghi đè dữ liệu mới bằng dữ liệu cũ hoặc bỏ sót một chuyển trạng thái quan trọng.

Khi tích hợp Spring Boot với Azure Service Bus, Event Hubs, AWS SQS, Kinesis hoặc Google Cloud Pub/Sub, cần xác định rõ **thứ tự được bảo đảm trong phạm vi nào** và **ứng dụng làm gì khi event đến muộn hoặc sai thứ tự**. Thứ tự trong một queue, partition, session hoặc ordering key không đồng nghĩa với thứ tự toàn hệ thống. Thứ tự broker giao cũng không tự bảo đảm thứ tự handler hoàn tất hay database commit.

Bài thuộc chương **Độ tin cậy** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt publish order, delivery order, processing order, commit order và business sequence.
2. Xác định phạm vi ordering: global, queue, partition, session, message group, ordering key hoặc aggregate.
3. Chọn partition key/session ID/ordering key phù hợp với invariant nghiệp vụ.
4. Giải thích vì sao consumer concurrency, retry và checkpoint có thể làm thay đổi thứ tự tác động.
5. Phân biệt event time, ingestion time và processing time.
6. Thiết kế cách xử lý event đến muộn: sequence/version guard, reorder buffer, watermark, allowed lateness và correction event.
7. Xử lý duplicate, missing sequence, gap, replay và event sai thứ tự mà không làm lùi trạng thái.
8. Hiểu khác biệt về ordering giữa Azure Service Bus/Event Hubs, AWS SQS/Kinesis và Google Cloud Pub/Sub.
9. Kiểm thử out-of-order delivery, late arrival, rebalance, retry và concurrency.
10. Theo dõi độ trễ, event age, sequence gap, late-event rate và số lần reorder.

## 2. Thứ tự có nhiều lớp

Một event đi qua nhiều bước:

~~~text
Producer tạo event
    → Publish request
    → Broker chấp nhận event
    → Broker lưu theo queue/partition/key
    → Consumer nhận event
    → Handler bắt đầu
    → Handler hoàn tất
    → Database commit
    → External side effect
    → ACK / Complete / Checkpoint
~~~

Các lớp thứ tự cần phân biệt:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Publish order** | Producer gọi publish theo thứ tự nào? | Producer gửi OrderCreated rồi OrderPaid |
| **Broker append order** | Broker ghi message vào log/queue theo thứ tự nào? | Hai event có sequence 10 và 11 cùng partition |
| **Delivery order** | Consumer nhận message theo thứ tự nào? | Message 10 được giao trước 11 |
| **Processing start order** | Handler nào bắt đầu trước? | Worker xử lý 10 và 11 song song |
| **Processing completion order** | Handler nào hoàn tất trước? | Event 11 xử lý xong trước event 10 |
| **Commit order** | Transaction database commit theo thứ tự nào? | State version 12 được ghi trước version 11 |
| **Business order** | Nghiệp vụ cho phép chuyển trạng thái theo thứ tự nào? | Không thể thanh toán trước khi đơn hàng được tạo |

Một broker có thể bảo đảm thứ tự append/delivery trong một phạm vi, nhưng ứng dụng vẫn phá vỡ thứ tự ở tầng xử lý nếu chạy nhiều handler đồng thời. Ngược lại, consumer có thể nhận event theo thứ tự đúng nhưng database transaction hoàn tất không theo thứ tự đó.

**Ordering guarantee luôn cần đi kèm phạm vi, điều kiện và failure behavior.** Không nên nói một dịch vụ có global ordering nếu tài liệu chỉ bảo đảm thứ tự trong partition, session hoặc key.

## 3. Phạm vi ordering: global, partition, session và key

### 3.1. Global ordering

Global ordering nghĩa là mọi event trong hệ thống có một thứ tự duy nhất được các consumer quan sát nhất quán.

Đây là yêu cầu đắt đỏ khi throughput và khả năng mở rộng tăng. Muốn có một thứ tự toàn cục, hệ thống thường cần một điểm tuần tự hóa hoặc một log duy nhất. Một queue/partition duy nhất có thể đơn giản hóa ordering nhưng giới hạn throughput, concurrency và khả năng mở rộng.

Chỉ yêu cầu global ordering khi nghiệp vụ thật sự cần. Nhiều hệ thống chỉ cần thứ tự theo đơn hàng, tài khoản, thiết bị hoặc aggregate.

### 3.2. Partition ordering

Partition là một luồng con có thứ tự trong một stream/log. Các event cùng partition được append theo thứ tự của partition. Nhiều partition có thể được xử lý song song.

Ví dụ:

~~~text
Partition 0: E1 → E2 → E3
Partition 1: E4 → E5
Partition 2: E6 → E7
~~~

Có thứ tự trong từng partition nhưng không có một thứ tự tổng quát giữa E3 và E4, hoặc giữa E5 và E6, trừ khi ứng dụng tự định nghĩa thêm sequence toàn cục.

### 3.3. Session hoặc message group

Một số broker hỗ trợ nhóm message theo session/message group. Consumer có thể xử lý tuần tự trong một nhóm, đồng thời nhiều nhóm vẫn chạy song song.

Ví dụ:

~~~text
Session ORDER-100: Created → Confirmed → Paid
Session ORDER-200: Created → Cancelled
Session ORDER-300: Created → Shipped
~~~

Thứ tự trong ORDER-100 không nói gì về thứ tự giữa ORDER-100 và ORDER-200. Đây thường là mô hình phù hợp khi mỗi aggregate có một chuỗi sự kiện riêng.

### 3.4. Ordering key / aggregate key

Ordering key là giá trị producer dùng để nhóm các event cần được xử lý theo thứ tự. Ví dụ dùng order ID, account ID hoặc device ID.

Nếu mọi event của một order có cùng key, chúng có thể được định tuyến tới cùng phạm vi ordering. Nhưng key không tự tạo ordering nếu broker chưa bật feature tương ứng hoặc consumer xử lý song song ngoài kiểm soát.

### Chọn phạm vi theo invariant

| Invariant nghiệp vụ | Phạm vi thường phù hợp |
| --- | --- |
| Mọi thay đổi số dư của một tài khoản phải tuần tự | Account ID |
| Mọi event của một đơn hàng phải đúng thứ tự | Order ID |
| Event của một thiết bị phải theo sequence thiết bị | Device ID |
| Các sự kiện độc lập có thể xử lý song song | Nhiều partition/key |
| Một workflow cần một bước toàn cục duy nhất | Workflow ID hoặc coordinator |
| Mọi event toàn hệ thống phải có một thứ tự duy nhất | Global sequencer/log, chỉ khi thực sự cần |

**Partition key phải phản ánh đơn vị cần tuần tự hóa.** Nếu chọn key quá rộng, nhiều event không liên quan bị dồn vào cùng partition và giảm throughput. Nếu chọn key quá hẹp, các event cần thứ tự có thể bị phân tán và mất ordering.

## 4. Partition key và vấn đề hot partition

Một partition key thường được hash hoặc ánh xạ tới partition/shard. Mọi event cùng key được đưa vào cùng phạm vi ordering theo cơ chế của dịch vụ.

Ví dụ:

- Dùng tenant ID có thể giữ thứ tự toàn bộ event của một tenant, nhưng một tenant lớn tạo hot partition.
- Dùng order ID phân tán tải tốt hơn và giữ thứ tự trong từng order.
- Dùng random UUID cho mỗi event giúp phân tán đều nhưng không giữ thứ tự giữa các event của cùng order.
- Dùng account ID phù hợp khi các thay đổi balance của một account phải tuần tự.

### Hot partition

Nếu một key nhận lượng event lớn hơn nhiều key khác, partition chứa key đó có thể trở thành bottleneck:

~~~text
Partition A: 90% traffic từ một tenant lớn
Partition B:  5% traffic
Partition C:  3% traffic
Partition D:  2% traffic
~~~

Tăng số partition không nhất thiết giải quyết hot key nếu mọi event của key đó vẫn phải đi cùng partition. Các lựa chọn:

- Giữ thứ tự theo aggregate nhỏ hơn nếu invariant cho phép.
- Tách loại event độc lập thành key khác.
- Giảm payload, batching hoặc chi phí xử lý.
- Scale consumer và capacity của partition trong giới hạn dịch vụ.
- Dùng sequence/version ở database để bảo vệ state khi cần xử lý song song.

Không chia một aggregate sang nhiều partition chỉ để tăng throughput nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt và không có cơ chế tái lập thứ tự.

## 5. Delivery order không bảo đảm processing order

Giả sử broker giao event theo thứ tự 41, 42, 43. Consumer có concurrency bằng 3:

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant W1 as Worker 1
    participant W2 as Worker 2
    participant W3 as Worker 3
    participant DB as Database
    B->>W1: Event 41
    B->>W2: Event 42
    B->>W3: Event 43
    W1->>DB: Xử lý chậm
    W2->>DB: Commit event 42
    W3->>DB: Commit event 43
    W1->>DB: Commit event 41
    Note over DB: Commit order 42 → 43 → 41
~~~

Nếu mỗi event thay thế trạng thái bằng snapshot mới, event 41 có thể ghi đè state mới hơn. Nếu event là delta, xử lý sai thứ tự có thể làm kết quả tính toán sai.

### Các nguồn làm đảo thứ tự

- Consumer xử lý song song nhiều message cùng key.
- Handler có thời gian xử lý khác nhau.
- Retry làm một event cũ được giao lại sau event mới.
- Worker crash và message được redeliver.
- Partition ownership thay đổi khi scale/rebalance.
- Batch listener xử lý các phần tử trong batch song song.
- Nhiều producer gửi cùng key nhưng không phối hợp sequence.
- Publisher retry làm một event cũ được append sau event mới.
- Checkpoint được ghi không theo thứ tự xử lý thực tế.

### Giữ thứ tự ở consumer

Nếu cần xử lý tuần tự theo key:

1. Dùng broker partition/session/ordering key phù hợp.
2. Chỉ có một luồng xử lý tuần tự trong phạm vi key/partition đó, hoặc dùng executor/keyed scheduler bảo toàn thứ tự.
3. Không ACK/complete trước khi transaction cần thiết hoàn tất.
4. Không cho retry event cũ chạy song song với event mới cùng aggregate nếu có thể làm sai state.
5. Dùng sequence/version guard ở nơi lưu trạng thái như lớp bảo vệ cuối.
6. Kiểm tra binder có tự tăng concurrency hoặc prefetch ngoài dự kiến không.

Tuần tự hóa giảm throughput trong phạm vi key, nhưng các key khác vẫn có thể chạy song song.

## 6. Event time, ingestion time và processing time

Event đến muộn thường chỉ có nghĩa là nó đến sau một event khác theo thứ tự quan sát của consumer. Để hiểu đúng “muộn”, cần phân biệt ba mốc thời gian:

| Thời gian | Ý nghĩa | Nguồn |
| --- | --- | --- |
| **Event time** | Thời điểm sự kiện thực tế xảy ra theo nghiệp vụ | Thiết bị, domain service hoặc nguồn dữ liệu |
| **Ingestion time** | Thời điểm broker/ingestion layer nhận event | Broker hoặc collector |
| **Processing time** | Thời điểm consumer xử lý event | Consumer runtime |

Ví dụ thiết bị đo nhiệt độ lúc 10:00 nhưng mất mạng và gửi dữ liệu lúc 10:07:

- Event time: 10:00.
- Ingestion time: 10:07.
- Processing time: 10:07 hoặc muộn hơn.

Nếu dashboard nhóm dữ liệu theo event time, bản ghi cần được gán vào cửa sổ 10:00 dù nó đến lúc 10:07. Nếu hệ thống chỉ dùng processing time, dữ liệu sẽ xuất hiện ở cửa sổ 10:07.

### Event timestamp không phải sequence

Timestamp có thể trùng, lệch đồng hồ hoặc đến từ nhiều nguồn không đồng bộ. Không nên dùng timestamp làm thứ tự tuyệt đối nếu nghiệp vụ cần thứ tự chắc chắn.

Ưu tiên:

- Aggregate sequence/version do nguồn dữ liệu có thẩm quyền cấp.
- Database commit version hoặc log offset trong phạm vi có thứ tự.
- Timestamp UTC để phân tích thời gian thực tế.
- Tie-breaker ổn định khi cần sắp xếp các event có cùng timestamp.

Dùng đồng hồ UTC để trao đổi event time. Trong một tiến trình JVM, dùng monotonic clock để đo thời lượng chờ/timeout; không dùng monotonic timestamp làm event time có thể chia sẻ giữa service.

## 7. Vì sao event đến muộn hoặc sai thứ tự?

Các nguyên nhân phổ biến:

- Thiết bị offline, buffer cục bộ rồi gửi bù.
- Mạng chập chờn hoặc retry nhiều lần.
- Producer có nhiều instance và sequence không được cấp thống nhất.
- Broker partition/session được phân phối không đúng key nghiệp vụ.
- Consumer scale/rebalance làm event được xử lý lại.
- Event cũ vào DLQ rồi được replay sau nhiều giờ/ngày.
- Batch upload chứa dữ liệu lịch sử.
- Một upstream service phát event sau khi workflow đã chuyển sang trạng thái mới.
- Đồng hồ thiết bị lệch hoặc timestamp bị tạo tại client.
- Một event phụ thuộc vào event trước nhưng event trước bị chậm hoặc mất.

Không phải event đến muộn nào cũng là lỗi. Dữ liệu lịch sử, thiết bị offline và event sourcing đều có thể tạo late event hợp lệ. Ứng dụng cần chính sách xác định event nào được chấp nhận, cập nhật, bỏ qua hoặc đưa vào điều tra.

## 8. Sequence number và version cho từng aggregate

Một event có thể mang metadata:

~~~json
{
  "eventId": "evt-7c9d",
  "aggregateType": "Order",
  "aggregateId": "ORD-10025",
  "aggregateVersion": 12,
  "eventType": "OrderPaid",
  "occurredAt": "2026-11-24T09:15:30Z",
  "schemaVersion": 2
}
~~~

Trong đó:

- eventId: định danh duy nhất của event.
- aggregateId: đối tượng nghiệp vụ mà event tác động.
- aggregateVersion: thứ tự event trong aggregate.
- occurredAt: thời điểm nghiệp vụ xảy ra.
- schemaVersion: phiên bản schema payload.

Sequence nên được cấp bởi nguồn có thẩm quyền và lưu bền vững cùng business change. Nếu hai producer độc lập tự tăng sequence mà không có atomic coordination, có thể tạo cùng version hoặc đảo thứ tự.

### Không dùng một sequence toàn cục nếu chỉ cần thứ tự theo aggregate

Một counter toàn cục có thể trở thành bottleneck. Nếu chỉ cần thứ tự theo order, dùng sequence riêng theo order. Nếu cần thứ tự theo account, sequence theo account. Sequence scope phải khớp invariant.

### Version guard trong database

Ví dụ bảng projection có cột last_event_version:

~~~sql
UPDATE order_projection
SET status = :new_status,
    last_event_version = :incoming_version
WHERE order_id = :order_id
  AND last_event_version = :incoming_version - 1;
~~~

Nếu update một row, event là version kế tiếp. Nếu không update được, có thể là:

- Duplicate/old event: version hiện tại đã bằng hoặc lớn hơn incoming version.
- Missing event/gap: incoming version lớn hơn version kế tiếp.
- Aggregate chưa được tạo.
- Có transaction cạnh tranh.

Phải đọc state hiện tại để phân loại; không coi mọi update count bằng 0 là duplicate.

### Phân biệt duplicate và gap

Giả sử last version hiện tại là 10:

| Incoming version | Diễn giải | Hành động gợi ý |
| ---: | --- | --- |
| 10 | Có thể là duplicate của event đã áp dụng | So sánh event ID/hash; bỏ qua nếu cùng event |
| 9 | Event cũ hơn | Bỏ qua hoặc audit theo policy |
| 11 | Event kế tiếp hợp lệ | Áp dụng |
| 12 | Thiếu version 11 | Buffer/retry/reconcile |
| 15 | Gap lớn | Kiểm tra nguồn, replay hoặc quarantine |

Nếu version 10 được dùng cho nhiều event trong một aggregate, cần sequence riêng từng event hoặc version semantics rõ ràng. Không giả định mỗi aggregate version luôn tăng đúng một cho mọi loại event nếu domain model không định nghĩa như vậy.

## 9. Chiến lược xử lý event đến muộn

Không có một chiến lược duy nhất. Chọn theo loại dữ liệu, khả năng đảo ngược và yêu cầu latency.

| Chiến lược | Cách làm | Phù hợp |
| --- | --- | --- |
| **Reject/quarantine** | Từ chối hoặc đưa event muộn vào hàng chờ điều tra | State transition không thể đảo ngược |
| **Ignore stale event** | Bỏ qua event có version thấp hơn state hiện tại | Snapshot/state projection có version |
| **Buffer and reorder** | Giữ event chờ sequence còn thiếu rồi xử lý theo thứ tự | Event có sequence và cần thứ tự nghiêm ngặt |
| **Apply with compensation** | Áp dụng event muộn bằng transaction/compensation | Workflow hỗ trợ sửa trạng thái |
| **Recompute from history** | Phát lại log để tính lại projection | Analytics, event-sourced projection |
| **Late correction event** | Phát event điều chỉnh thay vì sửa lịch sử | Ledger, reporting và audit |

### Chọn theo semantics nghiệp vụ

- **Ledger/tài chính:** không xóa hoặc ghi đè lịch sử; dùng correction/reversal event và đối soát.
- **Order state:** version guard; event cũ không được đưa state từ PAID về CREATED.
- **Telemetry/analytics:** có thể chấp nhận late event trong allowed-lateness window rồi cập nhật aggregate.
- **Inventory:** cần sequence hoặc transaction bảo vệ; không bỏ qua delta chỉ vì đến muộn.
- **Notification:** kiểm tra state hiện tại trước khi gửi; không gửi thông báo đã lỗi thời nếu trạng thái mới đã thay thế.

## 10. Buffer và reorder window

Khi event có sequence, consumer có thể giữ event đến sớm hơn thứ tự cần xử lý trong một buffer.

Ví dụ last applied version = 20, consumer nhận version 22 trước 21:

~~~text
Nhận version 22
    → Phát hiện gap: thiếu 21
    → Lưu 22 vào pending buffer
    → Chờ 21 trong reorder window
Nhận version 21
    → Áp dụng 21
    → Áp dụng 22
~~~

### Reorder buffer cần giới hạn

Mỗi buffer nên có:

- Key theo aggregate/partition.
- Giới hạn số event và tổng byte.
- Thời gian chờ tối đa.
- Retention cho event đang chờ.
- Cơ chế xử lý duplicate.
- Chính sách khi gap không được lấp đầy.
- Persist bền vững nếu process restart không được phép làm mất pending event.

Không chỉ giữ event trong RAM rồi ACK broker. Nếu process chết, buffer mất và event có thể bị thất lạc. Có thể lưu pending event vào database hoặc để broker tiếp tục giao lại, tùy thiết kế.

### Hết reorder window

Khi hết thời gian chờ mà event còn thiếu chưa đến:

- Yêu cầu producer/source replay version còn thiếu.
- Tra cứu snapshot mới nhất và rebuild projection nếu domain cho phép.
- Đưa aggregate vào trạng thái cần reconcile.
- Quarantine event nếu không thể xác định trạng thái an toàn.
- Không tự nhảy qua gap nếu các event bị thiếu có thể chứa side effect bắt buộc.

Reorder window là một chính sách latency/reliability trade-off, không phải bằng chứng event sẽ đến trong khoảng thời gian đó.

## 11. Watermark và allowed lateness trong xử lý stream

Trong stream processing, **watermark** là ước lượng tiến độ event time: hệ thống cho rằng các event có timestamp trước một mốc nhất định phần lớn đã đến. Watermark giúp đóng hoặc phát kết quả cho event-time window dù dữ liệu có thể đến không theo thứ tự.

Ví dụ cửa sổ 10:00–10:05, watermark đang ở 10:06:

- Event có event time 10:03 đến trước watermark: có thể được đưa vào window hiện tại.
- Event time 10:03 đến sau watermark: được xem là late event.
- Nếu allowed lateness là 2 phút, hệ thống có thể tiếp tục cập nhật window tới 10:08 theo engine semantics.

### Event-time window và processing-time window

| Loại window | Dựa trên | Kết quả |
| --- | --- | --- |
| **Event-time window** | Timestamp của sự kiện | Phản ánh thời điểm nghiệp vụ xảy ra, nhưng cần watermark/late handling |
| **Processing-time window** | Thời điểm consumer xử lý | Đơn giản, phù hợp metric vận hành; dữ liệu offline có thể nằm sai cửa sổ |
| **Ingestion-time window** | Thời điểm hệ thống nhận dữ liệu | Phản ánh thời điểm dữ liệu vào pipeline, không nhất thiết là lúc sự kiện xảy ra |

### Allowed lateness

Allowed lateness là khoảng thời gian hệ thống tiếp tục chấp nhận event đến muộn cho một window sau khi watermark đã đi qua window đó. Tùy engine, event muộn có thể cập nhật kết quả, phát update/retraction hoặc được gửi tới side output.

Không có một cấu hình watermark/allowed lateness chung cho mọi broker. Azure Event Hubs, Kinesis và Pub/Sub cung cấp stream/transport; watermark/window semantics thường thuộc stream processing engine như Apache Flink, Kafka Streams, Beam/Dataflow hoặc logic ứng dụng. Không nhầm broker retention/ack deadline với watermark.

### Chọn allowed lateness

- Dữ liệu telemetry từ thiết bị di động/offline có thể cần khoảng lateness dài hơn.
- Thanh toán/order event thường cần state transition và sequence guard hơn là chỉ gom theo timestamp.
- Dashboard realtime có thể phát kết quả tạm thời rồi cập nhật khi late event đến.
- Báo cáo đóng sổ có thể cần một thời điểm chốt và quy trình correction sau đó.

Khoảng allowed lateness quá ngắn làm mất dữ liệu đến chậm; quá dài làm tăng state retention, memory/storage và thời gian chốt kết quả.

## 12. Xử lý event muộn trong Spring Boot

Spring Boot consumer thường không có sẵn một watermark engine chỉ vì dùng Spring Cloud Stream. Ứng dụng cần xác định event metadata, sequence và policy.

Một event model minh họa:

~~~java
import java.time.Instant;
import java.util.UUID;

public record DomainEvent<T>(
        UUID eventId,
        String aggregateType,
        String aggregateId,
        long aggregateVersion,
        Instant occurredAt,
        int schemaVersion,
        T payload) {
}
~~~

Application service nên kiểm tra sequence trước khi thay đổi state:

~~~java
public enum ApplyResult {
    APPLIED,
    DUPLICATE,
    STALE,
    GAP,
    UNKNOWN_AGGREGATE
}
~~~

Pseudo-implementation:

~~~java
@Transactional
public ApplyResult apply(DomainEvent<OrderPaid> event) {
    OrderProjection current =
            repository.findForUpdate(event.aggregateId());

    if (current == null) {
        return ApplyResult.UNKNOWN_AGGREGATE;
    }

    long last = current.lastEventVersion();

    if (event.aggregateVersion() <= last) {
        return inbox.hasSameEvent(
                event.eventId(), event.aggregateId())
                ? ApplyResult.DUPLICATE
                : ApplyResult.STALE;
    }

    if (event.aggregateVersion() > last + 1) {
        pendingEvents.store(event);
        return ApplyResult.GAP;
    }

    repository.apply(event);
    inbox.markApplied(event.eventId(), event.aggregateId());
    return ApplyResult.APPLIED;
}
~~~

Đây là pseudocode định hướng, cần thiết kế transaction thật cẩn thận:

- findForUpdate cần row lock hoặc cơ chế optimistic concurrency tương đương.
- Inbox record và business state nên commit trong cùng transaction.
- Pending event phải được lưu bền vững trước khi ACK nếu consumer không thể nhận lại message.
- Khi nhận version kế tiếp, cần drain các pending event liên tiếp trong cùng transaction hoặc qua worker có kiểm soát.
- Nếu event cùng version nhưng ID khác, phải xác định domain có cho phép nhiều event cùng version hay không.
- Không ACK message bị gap nếu event chưa được lưu bền vững hoặc có cơ chế replay chắc chắn.

## 13. Azure Service Bus: Sessions và thứ tự trong session

Azure Service Bus hỗ trợ **Sessions** để nhóm message theo SessionId và xử lý tuần tự trong phạm vi session theo semantics của dịch vụ.

Ví dụ:

- SessionId = order ID.
- Các event của cùng order được gửi cùng session.
- Consumer nhận session lock và xử lý message của session theo thứ tự.
- Nhiều session khác nhau có thể được xử lý đồng thời bởi nhiều consumer.

### Điều sessions giúp giải quyết

- Nhóm các message liên quan thành một chuỗi.
- Hỗ trợ xử lý tuần tự theo session.
- Giữ session state theo khả năng của broker để hỗ trợ workflow.
- Giảm khả năng hai consumer cùng xử lý một session khi lock còn hiệu lực.

### Điều sessions không giải quyết

- Không tạo global ordering giữa mọi session.
- Không bảo vệ database/Blob/payment side effect khỏi duplicate.
- Session lock có thể hết hạn và message có thể redeliver.
- Publisher nhiều instance vẫn phải tạo thứ tự gửi đúng theo domain.
- Consumer có thể phá thứ tự nếu đưa message trong cùng session vào executor chạy song song.
- Event replay/republish cần giữ identity và version.

### Khi dùng sessions

1. Chọn SessionId theo aggregate cần tuần tự hóa.
2. Đảm bảo producer gửi event cùng aggregate với cùng SessionId.
3. Bật session-aware receiver/processor và xác minh cấu hình binder/native SDK.
4. Giữ xử lý trong session tuần tự nếu state phụ thuộc thứ tự.
5. Dùng idempotency/inbox để xử lý redelivery.
6. Đặt lock renewal, processing deadline và DLQ policy phù hợp.

Nếu một session có quá nhiều message hoặc một aggregate rất nóng, session đó có thể trở thành bottleneck. Tách session chỉ khi invariant nghiệp vụ cho phép.

## 14. Azure Event Hubs: thứ tự trong partition

Event Hubs là event streaming platform với partition. Event trong cùng partition có thứ tự append/sequence theo log của partition. Producer có thể dùng partition key để các event liên quan được định tuyến vào cùng partition theo cơ chế dịch vụ.

### Thiết kế partition key

- Dùng aggregate ID nếu cần thứ tự theo aggregate.
- Dùng key ổn định cho cùng nguồn event.
- Không dùng random key nếu cần thứ tự giữa các event của cùng đối tượng.
- Tránh key quá nóng nếu throughput một aggregate lớn.
- Không kỳ vọng thứ tự giữa các partition.

### Consumer và checkpoint

Consumer group đọc partition độc lập. Khi partition ownership chuyển giữa các processor, consumer có thể tiếp tục từ checkpoint đã lưu. Nếu xử lý song song nhiều event cùng partition và checkpoint không phản ánh đúng các event đã commit, có thể gây replay hoặc bỏ qua event.

Quy tắc:

- Commit business state trước checkpoint.
- Checkpoint chỉ tới vị trí mà mọi event trước đó trong partition đã được xử lý bền vững theo policy.
- Nếu xử lý song song, cần quản lý contiguous completion offset; không checkpoint vượt qua event còn đang chạy.
- Dùng inbox/version guard để xử lý replay sau crash/rebalance.
- Giữ thứ tự theo aggregate ở application layer nếu nhiều aggregate cùng partition nhưng cần xử lý song song.

Event Hubs partition ordering không tự đảm bảo business commit ordering khi consumer xử lý nhiều event song song.

## 15. AWS SQS: Standard và FIFO

### SQS Standard

SQS Standard cung cấp at-least-once delivery và best-effort ordering. Duplicate hoặc out-of-order delivery có thể xảy ra. Nếu nghiệp vụ yêu cầu thứ tự, cần sequence/version guard và xử lý idempotent.

Không giả định Standard queue có thể giữ thứ tự nghiệp vụ chỉ vì producer gọi SendMessage theo một thứ tự.

### SQS FIFO

SQS FIFO hỗ trợ ordering trong **MessageGroupId**:

- Các message trong cùng group được xử lý theo thứ tự FIFO theo semantics dịch vụ.
- Các group khác nhau có thể được xử lý song song.
- Message group nên phản ánh aggregate cần tuần tự hóa.
- Deduplication ID/cơ chế deduplication giảm duplicate send trong cửa sổ được dịch vụ hỗ trợ.

FIFO không tạo global ordering giữa các group. Consumer vẫn cần xử lý visibility timeout, redelivery, delete failure và side effect nghiệp vụ. Nếu ứng dụng tự xử lý song song nhiều message cùng group, phải bảo đảm không làm đảo commit order.

### Chọn MessageGroupId

| MessageGroupId | Kết quả |
| --- | --- |
| Một ID cố định cho toàn queue | Ordering rộng nhưng throughput/concurrency thấp |
| Tenant ID | Tuần tự theo tenant; tenant lớn có thể hot group |
| Order ID | Tuần tự theo order; các order chạy song song |
| Random ID mỗi message | Phân tán tốt nhưng không giữ thứ tự theo aggregate |

## 16. AWS Kinesis Data Streams: shard và sequence number

Kinesis Data Streams phân chia stream thành shard. Record có sequence number trong shard; các record được đọc theo thứ tự shard.

- Partition key ảnh hưởng shard mà record được định tuyến tới.
- Cùng partition key thường được ánh xạ vào cùng shard theo hash mapping hiện hành.
- Không có global ordering giữa nhiều shard.
- Consumer checkpoint sequence number theo shard.
- Resharding thay đổi topology shard và cần được consumer library xử lý.

### Xử lý song song

Nếu consumer nhận record theo thứ tự nhưng submit handler vào thread pool song song, commit có thể đảo thứ tự. Nếu checkpoint sau record mới trong khi record cũ chưa commit, restart có thể bỏ qua tác động của record cũ.

Dùng một trong các hướng:

- Xử lý tuần tự trong shard khi invariant yêu cầu.
- Keyed executor để tuần tự theo aggregate.
- Lưu sequence/version trong database để phát hiện gap/stale event.
- Quản lý checkpoint theo contiguous completed sequence, không vượt qua record chưa hoàn tất.
- Dùng inbox/idempotency để chống replay.

Kinesis ordering theo shard là nền tảng vận chuyển; application processing và commit vẫn cần được kiểm soát.

## 17. Google Cloud Pub/Sub: ordering keys

Pub/Sub hỗ trợ ordering key khi publisher/subscription được cấu hình phù hợp. Các message có cùng ordering key có thể được giao theo thứ tự publish trong phạm vi và điều kiện dịch vụ hỗ trợ.

### Điều kiện và phạm vi

- Ordering phải được bật cho subscription/client phù hợp.
- Publisher phải dùng ordering key nhất quán cho các message liên quan.
- Ordering guarantee có điều kiện theo region và cách publish; kiểm tra tài liệu dịch vụ hiện hành.
- Không có global ordering giữa các ordering key khác nhau.
- Redelivery/retry có thể ảnh hưởng tiến độ của các message cùng key.
- Consumer concurrency phải giữ thứ tự tác động nếu handler có side effect phụ thuộc event trước.

### Khi dùng ordering key

Dùng order ID cho event của một order, account ID cho event của một account. Không dùng một key chung cho mọi message nếu muốn throughput song song. Nếu một key nhận quá nhiều traffic, nó có thể trở thành hot key.

Exactly-once delivery và ordering key là hai tính năng có phạm vi khác nhau. Bật ordering không tự bảo vệ business state khỏi duplicate hoặc side effect ngoài Pub/Sub.

## 18. Spring Cloud Stream: partitioning và consumer concurrency

Spring Cloud Stream cung cấp abstraction function/consumer và binder. Khả năng partitioning, ordering, retry và settlement phụ thuộc binder và broker.

Ví dụ function consumer:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class OrderEventsConfiguration {

    @Bean
    Consumer<Message<DomainEvent<OrderChanged>>> orderChanged(
            OrderEventHandler handler) {
        return message -> handler.apply(message.getPayload());
    }
}
~~~

Function chỉ định cách gọi handler. Nó không tự tạo ordering. Cần cấu hình producer partition key hoặc native session/ordering key theo binder hỗ trợ.

### Những điều phải xác minh

- Binder có hỗ trợ partition key expression không?
- Partition count được provision hay binder tự tạo?
- Key được serialize/hash thế nào?
- Consumer concurrency có giới hạn theo partition/session không?
- Một key có thể được xử lý bởi nhiều thread cùng lúc không?
- Retry có giữ thứ tự hay đưa message về cuối queue?
- Khi exception, binder ACK, nack, abandon hoặc retry ra sao?
- Khi rebalance, in-flight handler và checkpoint được xử lý thế nào?
- Có hỗ trợ session/ordering key native của provider không?

Không coi cấu hình partitioning của Kafka binder có thể áp dụng trực tiếp cho Azure Service Bus, SQS hoặc Pub/Sub binder. Đọc đúng tài liệu/version và kiểm thử integration.

### Quy tắc thiết kế handler

- Handler nên chuyển event vào application service có sequence guard.
- Không chia nhỏ một message thành nhiều side effect bất đồng bộ rồi ACK trước khi các side effect được lưu bền vững.
- Nếu binder gọi handler đồng thời, dùng aggregate-level concurrency control.
- Nếu event bị gap, lưu pending state bền vững trước khi ACK hoặc để broker redeliver theo policy.
- Nếu event stale, ghi nhận metric/audit và bỏ qua theo domain rule.

## 19. Xử lý event muộn trong các loại nghiệp vụ

### Order và payment

Một OrderPaid version 8 đến sau OrderShipped version 9 không nhất thiết được bỏ qua. Có thể event version 9 không hợp lệ nếu chưa có payment, hoặc upstream sequence sai. Consumer cần đọc state, kiểm tra invariant và quyết định quarantine/reconcile.

Không dùng timestamp để tự động đặt status về trạng thái cũ. Dùng state transition hợp lệ và aggregate version.

### Inventory

Các event tăng/giảm tồn kho là delta. Nếu event cũ bị bỏ qua chỉ vì timestamp nhỏ hơn, số lượng có thể sai. Cần event ID deduplication và sequence/transaction để áp dụng mỗi delta đúng một lần.

### Telemetry

Event time thường quan trọng hơn arrival time. Dùng event-time window, watermark và allowed lateness. Late event có thể cập nhật kết quả thống kê hoặc tạo correction theo chính sách.

### Audit/ledger

Không ghi đè lịch sử để “sửa thứ tự”. Lưu event/correction mới, giữ audit trail và chạy reconciliation. Thứ tự hiển thị có thể dựa trên sequence có thẩm quyền, nhưng thời điểm thực tế vẫn lưu riêng.

### Notification

Trước khi gửi notification muộn, kiểm tra trạng thái mới nhất. Ví dụ event OrderReady đến sau OrderCancelled; không gửi thông báo “đơn đã sẵn sàng” nếu đơn hiện đã bị hủy, trừ khi business rule yêu cầu thông báo lịch sử.

## 20. Replay, DLQ và sự kiện lịch sử

Replay có thể đưa event cũ trở lại sau khi state đã tiến xa hơn. Đây là một nguồn late event có chủ đích.

### Replay cần giữ identity

- Giữ event ID gốc nếu đang phát lại cùng một event.
- Giữ aggregate ID và aggregate version.
- Ghi replay metadata riêng: replay batch ID, operator, thời điểm, lý do.
- Không thay occurredAt bằng thời điểm replay.
- Dùng consumer riêng/projection mới nếu mục tiêu là rebuild read model.
- Tránh replay trực tiếp vào side effect không idempotent như payment/email.

### Hai loại replay

| Loại replay | Mục tiêu | Cách xử lý |
| --- | --- | --- |
| **Operational retry** | Thử lại event chưa xử lý thành công | Giữ event identity; inbox/sequence guard tiếp tục áp dụng |
| **Projection rebuild** | Tính lại read model từ lịch sử | Dùng projection/version riêng hoặc reset có kiểm soát; tránh gửi lại external side effect |

DLQ replay không phải lúc nào cũng an toàn. Trước khi replay, xác minh event đã tạo side effect chưa, consumer version hiện tại có hiểu schema không, và event có còn hợp lệ với business state hiện tại không.

### Event schema evolution

Một event cũ có thể đến khi consumer đã nâng cấp schema. Cần:

- Version schema rõ ràng.
- Upcaster/adapter nếu cần.
- Giữ semantics của event cũ.
- Không thay đổi ý nghĩa timestamp/sequence khi chuyển đổi.
- Đưa payload không tương thích vào quarantine/DLQ thay vì diễn giải sai.

## 21. Ordering, idempotency và concurrency phải phối hợp

Một thiết kế vững thường dùng nhiều lớp:

| Rủi ro | Cơ chế |
| --- | --- |
| Broker giao sai thứ tự ngoài phạm vi guarantee | Partition/session/ordering key hoặc sequence guard |
| Handler hoàn tất sai thứ tự | Sequential executor hoặc keyed serialization |
| Event được giao lại | Inbox/idempotency key |
| Event cũ ghi đè state mới | Aggregate version/optimistic concurrency |
| Thiếu event giữa sequence | Gap detection, buffer, replay/reconciliation |
| Event đến muộn theo event time | Watermark/allowed lateness/correction |
| Replay tạo side effect trùng | Event ID ổn định, side-effect idempotency |
| Worker cũ ghi sau khi lease hết | Fencing/version check |
| Checkpoint vượt event chưa commit | Contiguous completion tracking |

Không dùng lock để thay thế mọi cơ chế. Lock điều phối concurrency trong thời gian nhất định; sequence/version và unique constraint bảo vệ state bền vững.

## 22. Observability: đo thứ tự và độ trễ

Metrics nên theo dõi:

| Metric | Ý nghĩa |
| --- | --- |
| event_delivery_lag_seconds | Thời gian từ broker publish/ingest tới delivery |
| event_processing_lag_seconds | Thời gian từ delivery tới handler start/commit |
| event_age_seconds | Thời gian từ occurredAt tới processing |
| late_event_total | Số event đến sau ngưỡng event-time hoặc watermark |
| out_of_order_event_total | Số event có sequence thấp hơn hoặc cao hơn dự kiến |
| sequence_gap_total | Số lần phát hiện thiếu sequence |
| stale_event_ignored_total | Số event cũ bị bỏ qua theo policy |
| reorder_buffer_depth | Số event đang chờ sequence trước |
| reorder_wait_seconds | Thời gian event nằm trong buffer |
| partition_hotspot | Mức mất cân bằng tải giữa partition/key |
| checkpoint_lag | Khoảng cách giữa event đã commit và checkpoint |
| replay_total | Số event được phát lại |

Cần thống nhất timestamp và định nghĩa metric. Event age dùng event time từ nguồn có thẩm quyền; delivery lag dùng timestamp broker nếu có; processing duration dùng monotonic clock trong process.

### Log/trace

Ghi có kiểm soát:

- Event ID, aggregate ID và aggregate version.
- Partition/session/ordering key đã được masking hoặc giới hạn.
- OccurredAt, ingestion time và processing time.
- Delivery count, retry attempt và replay batch ID.
- Last applied version và incoming version khi phát hiện gap/stale event.
- Handler duration, commit result và checkpoint/ACK result.

Không dùng aggregate ID, message ID hoặc tenant ID làm metric label có cardinality rất cao. Đưa thông tin chi tiết vào log/trace với retention và masking phù hợp.

## 23. Kiểm thử ordering và late events

Một test chỉ gửi message tuần tự rồi xác nhận handler thành công chưa chứng minh ordering đúng. Cần tạo các tình huống đảo thứ tự có chủ đích.

### Test matrix

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Hai event cùng aggregate, version liên tiếp | Commit đúng thứ tự hoặc version guard chặn sai thứ tự |
| Version 12 đến trước version 11 | Phát hiện gap; buffer/retry/reconcile theo policy |
| Version 10 đến sau khi state đã ở 12 | Bỏ qua/audit nếu là stale duplicate |
| Cùng event ID được giao lại | Inbox nhận diện duplicate |
| Cùng version nhưng event ID khác | Áp dụng domain rule; không âm thầm coi là duplicate |
| Hai aggregate khác nhau | Có thể xử lý song song |
| Một aggregate hot key | Quan sát throughput/lag và không làm mất thứ tự |
| Consumer restart/rebalance | Replay không làm side effect trùng |
| Checkpoint lỗi sau DB commit | Event có thể đọc lại nhưng inbox bảo vệ state |
| Late telemetry trong allowed lateness | Window được cập nhật theo policy |
| Event đến sau watermark và hết allowed lateness | Side output/correction/quarantine theo policy |
| DLQ replay event cũ | Giữ event identity và không lặp side effect |

### Failure injection

1. Làm event version 2 xử lý nhanh hơn version 1.
2. Kill worker sau commit nhưng trước ACK/checkpoint.
3. Để lock/visibility/ack deadline hết hạn khi handler đang chạy.
4. Gửi event cũ sau khi aggregate đã chuyển trạng thái mới.
5. Tạo gap bằng cách không phát version kế tiếp.
6. Replay event từ DLQ sau nhiều giờ.
7. Tăng consumer concurrency và scale/rebalance.
8. Giả lập clock skew giữa producer và consumer.
9. Gửi nhiều event cùng ordering key để đo hot key.
10. Kiểm tra watermark và allowed lateness bằng event time có kiểm soát.

### Test trên managed service

- Dùng queue/topic/stream test riêng.
- Chạy đúng binder/native SDK và cấu hình partition/session/key.
- Xác minh thứ tự broker quan sát được bằng sequence/offset/delivery metadata.
- Đọc database để xác nhận commit order và aggregate version.
- Kiểm tra redelivery, checkpoint, DLQ và replay.
- Không dùng production queue/stream để cố ý tạo gap, replay hoặc hết lock.

## 24. Bài thực hành: xử lý Order events sai thứ tự

**Bối cảnh:** Spring Boot Order Projection nhận OrderCreated, OrderConfirmed, OrderPaid và OrderCancelled từ một broker managed. Mỗi event có order ID, event ID, aggregate version và occurredAt. Event có thể bị retry, redeliver hoặc đến sai thứ tự.

### Phần A — Xác định ordering scope

1. Xác định aggregate cần tuần tự hóa là Order ID.
2. Chọn Service Bus SessionId, SQS FIFO MessageGroupId, Event Hubs/Kinesis partition key hoặc Pub/Sub ordering key phù hợp.
3. Ghi rõ phạm vi guarantee và điều kiện của broker.
4. Xác định consumer concurrency trong một key/partition/session.
5. Ghi rõ event nào có thể xử lý song song.

### Phần B — Xây dựng sequence guard

1. Lưu last_event_version trong order projection.
2. Áp dụng event kế tiếp bằng conditional update/transaction.
3. Nếu version nhỏ hơn hoặc bằng hiện tại, kiểm tra duplicate/stale.
4. Nếu version lớn hơn current + 1, lưu pending event hoặc kích hoạt replay.
5. Khi gap được lấp đầy, drain pending event theo thứ tự.
6. Không để event cũ ghi đè state mới hơn.

### Phần C — Late event policy

1. Với OrderPaid đến sau OrderCancelled, kiểm tra domain invariant và đưa vào reconciliation nếu mâu thuẫn.
2. Với event telemetry, dùng event time và allowed lateness.
3. Với audit/ledger, phát correction event thay vì sửa lịch sử.
4. Với notification, kiểm tra state hiện tại trước khi gửi.

### Phần D — Kiểm thử và vận hành

1. Gửi version 1, 3, 2 và xác minh state cuối.
2. Gửi version 2 hai lần và xác minh idempotency.
3. Kill consumer sau commit trước ACK/checkpoint.
4. Replay version cũ từ DLQ.
5. Tăng concurrency và kiểm tra commit order.
6. Theo dõi late-event rate, sequence gap, reorder buffer và processing lag.

### Sản phẩm cần nộp

- Bảng ordering guarantee theo broker và phạm vi key/partition/session.
- Event schema có event ID, aggregate ID, version và occurredAt.
- Sơ đồ delivery/processing/commit/checkpoint.
- Sequence guard và chính sách gap/late event.
- Kết quả test out-of-order, duplicate, replay và consumer restart.
- Dashboard metrics về event age, late events, sequence gap và partition hotspot.

### Câu hỏi tự kiểm tra

1. Vì sao delivery order không bảo đảm commit order?
2. Global ordering khác partition ordering như thế nào?
3. Khi nào nên chọn order ID làm partition/session/ordering key?
4. Vì sao một key quá nóng có thể giới hạn throughput?
5. Event time khác ingestion time và processing time ra sao?
6. Vì sao timestamp không phải lúc nào cũng là sequence đáng tin cậy?
7. Version guard phân biệt duplicate, stale event và gap như thế nào?
8. Khi version 12 đến trước version 11, vì sao không nên luôn bỏ qua version 12?
9. Watermark và allowed lateness thuộc broker hay stream processing engine?
10. Azure Service Bus Sessions khác Event Hubs partition ordering thế nào?
11. SQS FIFO MessageGroupId bảo đảm thứ tự trong phạm vi nào?
12. Vì sao Pub/Sub ordering key không tạo global ordering?
13. Checkpoint vượt qua event chưa commit có thể gây hậu quả gì?
14. Replay event cũ cần giữ những identity/metadata nào?
15. Làm sao xử lý late payment/order event mà không ghi lùi trạng thái?

## 25. Ghi nhớ

- Ordering phải được mô tả theo phạm vi: global, partition, session, message group, ordering key hoặc aggregate.
- Publish order, broker append/delivery order, processing order và database commit order là các lớp khác nhau.
- Consumer concurrency, retry, redelivery và checkpoint có thể làm đảo thứ tự tác động dù broker giao đúng thứ tự.
- Chọn key theo aggregate cần tuần tự hóa; key quá rộng tạo hot partition, key quá hẹp làm mất ordering cần thiết.
- Event time, ingestion time và processing time có mục đích khác nhau. Timestamp không thay thế sequence/version có thẩm quyền.
- Dùng aggregate version, conditional update và gap detection để ngăn event cũ ghi đè state mới.
- Late event có thể được buffer/reorder, bỏ qua theo version, áp dụng correction hoặc đưa vào reconciliation; chọn theo invariant nghiệp vụ.
- Watermark/allowed lateness là khái niệm stream processing; không đồng nhất với broker retention, lock hoặc ack deadline.
- Service Bus Sessions, Event Hubs partitions, SQS FIFO message groups, Kinesis shards và Pub/Sub ordering keys có phạm vi guarantee khác nhau.
- Kiểm thử event sai thứ tự, duplicate, gap, late arrival, replay, rebalance và commit/checkpoint; đo event age, processing lag và sequence gap.

## Tài liệu tham khảo

- [Azure Service Bus sessions](https://learn.microsoft.com/azure/service-bus-messaging/message-sessions)
- [Azure Event Hubs features and partitions](https://learn.microsoft.com/azure/event-hubs/event-hubs-features)
- [AWS SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues.html)
- [Amazon Kinesis Data Streams partition keys](https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html)
- [Google Cloud Pub/Sub message ordering](https://cloud.google.com/pubsub/docs/ordering)
- [Google Cloud Pub/Sub flow control](https://cloud.google.com/pubsub/docs/flow-control)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Apache Flink event time and watermarks](https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/time/)
- [Apache Beam programming guide: watermarks and late data](https://beam.apache.org/documentation/programming-guide/#watermarks-and-late-data)
- [Martin Fowler — Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
