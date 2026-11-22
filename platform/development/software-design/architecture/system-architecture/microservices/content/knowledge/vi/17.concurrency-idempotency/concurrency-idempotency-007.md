# Thứ tự theo khóa nghiệp vụ và giới hạn bảo đảm toàn cục

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Đồng thời và lặp an toàn  
> **Trọng tâm:** Xác định phạm vi ordering có ý nghĩa trong nghiệp vụ, tổ chức xử lý theo business key, bảo vệ phiên bản trạng thái và hiểu giới hạn của các bảo đảm thứ tự khi nhiều service, partition và worker cùng hoạt động.

## 1. Mục tiêu học tập

Sau bài học, người đọc có thể:

- Phân biệt total order, per-key order, per-partition order, causal order và best-effort order.
- Chọn business key đúng cho thao tác: orderId, accountId, customerId, seatId, SKU, tenantId hoặc resourceId.
- Giải thích vì sao thứ tự message trong broker không tự bảo đảm thứ tự hiệu ứng ở consumer hoặc thứ tự cuối cùng giữa nhiều service.
- Thiết kế partitioning và consumer concurrency để các sự kiện cùng aggregate được xử lý theo trình tự cần thiết.
- Dùng aggregate version/sequence, optimistic concurrency, conditional update và state machine để từ chối cập nhật cũ hoặc sai thứ tự.
- Phân biệt event time, processing time, commit order và quan hệ nhân quả; không dùng timestamp của nhiều máy làm bằng chứng duy nhất về thứ tự.
- Xử lý duplicate, out-of-order delivery, retry, dead-letter, replay và partition rebalance.
- Nhận diện khi per-key ordering không đủ vì invariant liên quan nhiều key, nhiều service hoặc quota toàn cục.
- Đánh giá chi phí của global sequencing/serialization và chọn cơ chế có thể chứng minh đúng với throughput, availability và độ trễ của hệ thống.

## 2. Tình huống mở đầu: hai thao tác trên cùng một đơn hàng

Một đơn hàng có state machine:

~~~text
CREATED → PAID → PACKING → SHIPPED → DELIVERED
                 |
                 +→ CANCELLED (chỉ khi thỏa điều kiện)
~~~

Hai sự kiện được tạo gần nhau:

- PaymentCaptured(order-101) xác nhận tiền đã được thu.
- CancelRequested(order-101) yêu cầu hủy đơn.

Nếu hai consumer xử lý đồng thời, cả hai có thể đọc trạng thái CREATED rồi ghi kết quả khác nhau:

~~~text
Worker A                         Worker B
   |                                |
   | PaymentCaptured                | CancelRequested
   v                                v
đọc order=CREATED                đọc order=CREATED
   |                                |
   v                                v
ghi PAID                          ghi CANCELLED
   |                                |
   +------------- race -------------+
~~~

Tùy thứ tự commit, bản ghi có thể thành CANCELLED dù payment đã capture, hoặc PAID dù lệnh hủy hợp lệ đã được xử lý trước đó. Một event cũ ghi đè state mới có thể gây side effect sai như đóng gói hàng đã hủy hoặc hoàn tiền hai lần.

**Câu hỏi thiết kế:** thứ tự nào thực sự cần được bảo đảm? Theo orderId, customerId, toàn bộ hệ thống, hay quan hệ nhân quả giữa các thao tác? Không có một thứ tự duy nhất phù hợp cho mọi loại dữ liệu.

## 3. Ordering có nhiều phạm vi

### 3.1. Total order

Mọi sự kiện trong phạm vi được xét có một thứ tự duy nhất:

~~~text
E1 < E2 < E3 < E4 < E5
~~~

Tất cả consumer tuân theo cùng một thứ tự. Total order hữu ích khi mọi thao tác cạnh tranh trên cùng một tài nguyên logic hoặc domain thật sự cần một sequencer chung. Nó thường đắt về throughput và khả năng sẵn sàng vì cần một điểm hoặc nhóm điều phối thứ tự.

### 3.2. Per-key order

Chỉ các sự kiện cùng business key cần theo thứ tự:

~~~text
order-101: E1 → E2 → E3
order-102: A1 → A2
order-103: B1 → B2 → B3
~~~

Các key khác nhau có thể xử lý song song. Đây là mô hình hữu ích cho aggregate như order, account, shipment hoặc seat.

### 3.3. Per-partition order

Broker như Kafka giữ thứ tự append trong một partition:

~~~text
Partition 0: E1 → E2 → E3
Partition 1: A1 → A2
Partition 2: B1 → B2
~~~

Consumer đọc records trong partition theo offset, nhưng ứng dụng có thể phá effective processing order nếu dispatch nhiều records cùng partition sang thread bất đồng bộ rồi commit/ghi kết quả không theo trình tự. Ordering của broker chỉ là một lớp trong pipeline.

### 3.4. Causal order

Nếu B được tạo ra vì A đã xảy ra, B phải được xử lý sau A trong phạm vi quan hệ nhân quả đó:

~~~text
OrderCreated → PaymentRequested → PaymentCaptured → OrderPaid
~~~

Hai sự kiện không liên quan có thể không cần một thứ tự tương đối. Causal order tránh buộc toàn hệ thống phải thống nhất thứ tự của mọi sự kiện độc lập.

### 3.5. Best-effort hoặc unordered

Các sự kiện độc lập như metric, telemetry hoặc notification có thể xử lý không theo thứ tự nếu contract cho phép. Consumer vẫn cần idempotency/deduplication, nhưng không cần giữ toàn bộ stream tuần tự.

## 4. Chọn business key đúng

Business key xác định **những thao tác nào tranh cùng một trạng thái hoặc invariant**.

| Business key | Các thao tác thường cần thứ tự | Ví dụ |
| --- | --- | --- |
| orderId | State transitions của một đơn | Paid, cancel, pack, ship |
| accountId | Ghi nợ/ghi có trên một sổ tài khoản | Debit, credit, hold, release |
| seatId | Giữ/chốt/hủy cùng ghế | Reserve, confirm, expire |
| sku + warehouseId | Thay đổi lượng tồn ở một kho | Reserve, receive, allocate |
| customerId | Một số quy tắc hạn mức theo khách | Coupon quota, profile sequence |
| tenantId | Quota hoặc cấu hình chung của tenant | API quota, tenant policy |
| aggregateId | Event sequence của một aggregate | Domain event stream |

### 4.1. Key quá rộng làm mất song song

Nếu dùng tenantId làm partition key cho mọi thao tác của một tenant lớn, tất cả order của tenant đó đi vào cùng partition/worker. Một tenant có traffic lớn trở thành hot key, hạn chế throughput dù các order độc lập.

### 4.2. Key quá hẹp không bảo vệ invariant

Nếu campaign chỉ có 100 voucher nhưng partition theo customerId, hai trăm khách khác nhau có thể cùng cạnh tranh quota. Per-customer order không bảo đảm tổng campaign không vượt 100.

### 4.3. Một thao tác có thể cần nhiều phạm vi thứ tự

Checkout có thể cần:

- orderId để tuần tự hóa state transition của đơn.
- sku + warehouseId để bảo vệ stock.
- paymentAccountId để bảo vệ payment operation.
- campaignId để bảo vệ quota khuyến mại.

Không thể chọn một key duy nhất và kỳ vọng nó bảo vệ mọi invariant. Cần owner và transaction/coordination ở từng resource boundary.

### 4.4. Chọn key theo invariant, không theo DTO thuận tiện

Hãy hỏi: “Nếu hai request khác key chạy cùng lúc, chúng có thể vi phạm cùng một điều kiện nghiệp vụ không?” Nếu có, key hiện tại có thể chưa đủ hoặc invariant cần được bảo vệ ở một owner/transaction chung khác.

## 5. Những mức bảo đảm và giới hạn

| Guarantee | Bảo đảm điều gì | Không bảo đảm điều gì |
| --- | --- | --- |
| FIFO trong một queue đơn | Consumer nhận phần tử theo thứ tự enqueue của queue đó | Nhiều queue, nhiều producer hoặc side effect ngoài queue |
| Per-partition ordering | Record cùng partition theo offset | Ordering giữa partitions; completion order nếu consumer xử lý song song |
| Per-key ordering | Cùng key đi qua một lane có thứ tự | Invariant giữa nhiều key hoặc nhiều service |
| Aggregate version | Không áp dụng state transition cũ hơn version hiện tại | Không tự tạo thứ tự toàn cục giữa aggregates |
| Causal ordering | Quan hệ phụ thuộc được tôn trọng | Thứ tự cho mọi cặp event độc lập |
| Global total order | Một thứ tự chung trong phạm vi xác định | Không miễn phí; có chi phí coordination/availability |
| Timestamp sort | Sắp theo trường thời gian được ghi | Không chứng minh thứ tự commit/causality nếu clock lệch hoặc timestamp trùng |

### 5.1. Không có ordering toàn hệ thống tự nhiên

Mỗi service có database, clock, queue và transaction riêng. Không có một đồng hồ toàn cầu tuyệt đối và không có thứ tự commit toàn cục tự sinh chỉ vì messages mang timestamp.

Nếu business không yêu cầu thứ tự giữa hai order độc lập, ép chúng vào một global queue thường làm giảm throughput mà không tăng tính đúng.

### 5.2. Contract ordering phải ghi rõ phạm vi

Một tuyên bố như “events are ordered” chưa đủ. Contract cần nêu:

- Ordered theo key nào?
- Trong topic, partition, aggregate hay workflow nào?
- Thứ tự được xác lập lúc nhận, lúc commit hay lúc publish?
- Duplicate có thể xảy ra không?
- Consumer xử lý song song tới mức nào?
- Khi retry/DLQ, thứ tự được phục hồi ra sao?
- Version/sequence được giữ trong bao lâu?

## 6. Timestamp không phải thứ tự commit

Một event có thể chứa:

~~~json
{
  "eventType": "PaymentCaptured",
  "orderId": "order-101",
  "occurredAt": "2026-11-11T10:00:00.100Z"
}
~~~

Timestamp không đủ làm bằng chứng ordering vì:

- Clock của hai instance lệch nhau.
- Precision chỉ đến millisecond nên nhiều event cùng timestamp.
- Event được tạo trước nhưng transaction commit sau.
- Message bị retry/publish trễ.
- Replay giữ timestamp lịch sử nhưng processing time là hiện tại.
- Timestamp đến từ client, gateway, service hoặc database khác nhau.

### 6.1. Phân biệt các mốc thời gian

| Trường | Ý nghĩa |
| --- | --- |
| occurredAt | Thời điểm nghiệp vụ được cho là xảy ra tại source |
| committedAt | Thời điểm thay đổi được commit ở owner database, nếu đo được |
| publishedAt | Thời điểm relay/broker nhận event |
| processedAt | Thời điểm consumer xử lý |

Không gộp chúng thành một timestamp chung nếu hệ thống cần chẩn đoán latency hoặc thứ tự.

### 6.2. Timestamp hữu ích nhưng không thay sequence

Timestamp phù hợp cho audit, UX, time-window analytics và debugging. Để bảo vệ thứ tự state transition của aggregate, dùng sequence/version do owner cấp trong transaction.

### 6.3. Wall clock và monotonic clock

- Wall clock/UTC timestamp phù hợp lưu mốc thời gian và so sánh deadline theo policy.
- Monotonic clock phù hợp đo elapsed duration trong một process.
- Monotonic counter/version phù hợp biểu diễn thứ tự logical trong phạm vi owner.

Không so trực tiếp monotonic clock value giữa hai process; không dùng UTC timestamp đơn lẻ làm fencing token.

## 7. Aggregate sequence và version

Một aggregate có thể mang version tăng dần:

~~~text
order-101:
  version=1  OrderCreated
  version=2  PaymentAuthorized
  version=3  OrderConfirmed
  version=4  PackingStarted
~~~

Mỗi lần owner commit một transition hợp lệ, version tăng một. Consumer nhận event có thể biết event nào cũ, event nào kế tiếp và event nào bị thiếu.

Envelope minh họa:

~~~json
{
  "eventId": "evt-903",
  "eventType": "OrderConfirmed",
  "aggregateType": "Order",
  "aggregateId": "order-101",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-11T10:00:03Z",
  "correlationId": "saga-101",
  "causationId": "cmd-552",
  "payload": {
    "orderId": "order-101",
    "status": "CONFIRMED"
  }
}
~~~

### 7.1. Version được cấp tại owner

Không để consumer suy sequence từ timestamp. Owner cập nhật version cùng state trong transaction:

~~~sql
UPDATE orders
SET status = :next_status,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :order_id
  AND status = :expected_status
  AND version = :expected_version;
~~~

Nếu affected rows = 1, transition đã thắng. Nếu bằng 0, state/version đã thay đổi hoặc precondition không còn đúng. Application đọc lại state để phân loại conflict, retry có điều kiện hoặc trả 409.

Event/outbox phải ghi cùng transaction và mang version đã commit.

### 7.2. Optimistic locking không phải queue

Version giúp phát hiện stale write, nhưng không bảo đảm mọi request đến theo thứ tự. Nếu command version 4 đến trước version 3, service có thể từ chối 4 do expectedVersion mismatch; caller cần query/retry sau khi state phù hợp.

### 7.3. Version gap

Consumer đang có version 3 nhận version 5. Nó chưa thấy version 4. Có thể:

- Version 4 chưa tới.
- Event 4 đang retry hoặc bị lỗi.
- Event không được phát vì bug.
- Contract không yêu cầu mọi version phải xuất hiện trong stream consumer đó.

Nếu event là delta cần áp dụng tuần tự, không nên bỏ qua gap. Có thể buffer, retry, query owner snapshot hoặc reconciliation. Nếu event là full snapshot với semantics “state tại version 5”, có thể áp dụng version mới hơn theo contract; không áp dụng quy tắc này cho event delta.

## 8. Kafka: ordering trong partition

Kafka sắp xếp record theo offset trong từng partition. Producer gửi các record cùng key thường được partitioner đưa về cùng partition, nếu partitioning strategy và topology tương thích.

~~~text
Topic: order-events
  Partition 0: order-101 v1 → order-101 v2 → order-101 v3
  Partition 1: order-102 v1 → order-102 v2
  Partition 2: order-103 v1 → order-103 v2
~~~

Ví dụ key là orderId. Các order khác nhau được xử lý song song; events của cùng order đi chung lane.

### 8.1. Producer record key

~~~java
ProducerRecord<String, OrderEvent> record =
    new ProducerRecord<>(
        "order-events",
        event.orderId(),
        event
    );

kafkaTemplate.send(record);
~~~

Đây là ví dụ Spring Kafka. Serializer, topic, producer configuration, transaction và exception handling cần phù hợp với ứng dụng.

### 8.2. Kafka ordering không tự bảo đảm toàn pipeline

- Không có total order giữa các partitions.
- Consumer có thể dispatch cùng partition records sang executor khác nhau rồi hoàn tất sai thứ tự.
- Hai producer độc lập cùng gửi key có thể cạnh tranh; cần sequence/transactional ownership nếu business order phải rõ.
- Retry/DLT/replay có thể đưa record cũ trở lại sau record mới.
- Thay partition count có thể remap key; record cũ còn ở partition cũ, record mới sang partition mới, nên không có thứ tự xuyên hai partition tự nhiên.
- Consumer side effects có thể commit ngoài database trước khi offset commit, dẫn tới duplicate sau restart.

**Broker order là một bảo đảm hẹp; end-to-end business order cần được kiểm soát thêm.**

### 8.3. Partition count thay đổi

Giả sử order-101 trước đây map vào partition 1. Sau khi tăng partition count, partitioner có thể map key này sang partition 4. Event cũ vẫn ở partition 1, event mới ở partition 4. Consumer group xử lý hai partitions độc lập; không có guarantee rằng event cũ luôn hoàn tất trước event mới.

Nếu per-key ordering là yêu cầu cứng, phải có chiến lược migration: drain topic cũ, versioned topic, routing epoch, stable partition mapping hoặc owner version validation. Không tăng partition count mà bỏ qua tác động đến key affinity.

### 8.4. Consumer group và ownership partition

Trong một consumer group, partition được gán cho consumer; rebalance có thể chuyển ownership. Consumer phải xử lý in-flight work, commit offset đúng và tránh worker cũ tiếp tục side effect sau khi mất ownership.

Dù broker chỉ giao partition cho một consumer tại một thời điểm, consumer code vẫn có thể phá order nếu tạo nhiều async tasks không được serialize.

## 9. Effective processing order ở consumer

Một consumer có thể đọc tuần tự:

~~~text
poll offsets: 10, 11, 12
dispatch async:
  offset 10 → slow worker
  offset 11 → fast worker
  offset 12 → fast worker

completion:
  11, 12, 10
~~~

Broker deliver order đúng nhưng side effects hoàn tất ngược. Nếu records cùng aggregate, consumer phải:

- Xử lý tuần tự theo partition hoặc key lane.
- Hoặc dùng aggregate version/CAS để từ chối stale transitions.
- Commit offset chỉ khi semantics xử lý và retry đã được bảo đảm.
- Dùng bounded concurrency và backpressure.
- Không để task cũ tiếp tục ghi sau rebalance mà không có fencing/version checks.

### 9.1. Commit offset sớm nguy hiểm

Nếu consumer commit offset 12 trước khi offset 10/11 xử lý xong, crash có thể khiến side effects chưa hoàn tất nhưng broker không giao lại chúng. Cần hiểu cơ chế commit và asynchronous acknowledgements của framework.

### 9.2. Commit offset muộn có thể tạo duplicate

Nếu side effect database đã commit nhưng offset chưa commit, restart khiến record được giao lại. Consumer cần inbox/deduplication hoặc idempotent state transition.

### 9.3. Parallelize giữa keys

Có thể dùng nhiều lane:

~~~text
order-101 lane 0: v1 → v2 → v3
order-102 lane 1: v1 → v2
order-103 lane 2: v1 → v2
~~~

Nhưng phải bảo đảm hai records cùng key không chạy đồng thời, và lane rebalance/failure có cơ chế phục hồi. Hashing key vào một thread trong process chỉ bảo đảm local ordering trong vòng đời process; nhiều replicas vẫn cần broker/owner state.

## 10. Transactional outbox và thứ tự publish

Outbox bảo vệ việc thay đổi state và ghi ý định phát event trong cùng transaction:

~~~text
BEGIN DB TRANSACTION
  UPDATE order state, version=5
  INSERT outbox(order-101, version=5, event)
COMMIT
~~~

Outbox relay publish event. Nếu có nhiều relay workers, chúng có thể đọc hai rows của cùng aggregate và publish version 5 trước version 4 nếu không có claim/ordering policy.

### 10.1. Giữ thứ tự trong relay

Các cách có thể dùng:

- Claim/serialize theo aggregateId.
- Chỉ publish event kế tiếp của aggregate khi event trước đã được xác nhận.
- Partition outbox work theo stable hash aggregateId.
- Dùng sequence và consumer kiểm gap/version.
- Publish vào broker với key=aggregateId để cùng key vào một partition.

Không cần tuần tự hóa toàn bộ outbox. Có thể chạy song song giữa aggregates, giữ thứ tự trong từng aggregate.

### 10.2. Relay vẫn có thể publish lặp

Relay có thể publish thành công rồi crash trước khi đánh dấu sent. Lần chạy sau publish lại. Consumer phải dedupe eventId/aggregateVersion và bảo vệ side effects.

### 10.3. Không sort chỉ bằng createdAt

Nhiều relay workers có thể claim, retry và publish trễ. createdAt không đủ chứng minh version order. Dùng aggregate sequence và relay policy.

## 11. Inbox, deduplication và xử lý event cũ

Một inbox table có thể lưu:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    aggregate_version BIGINT,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer xử lý trong một transaction:

~~~text
BEGIN
  INSERT inbox(eventId)
  if duplicate:
      return already processed

  verify aggregate version/state
  apply local business change
  write own outbox if needed
COMMIT
ack broker
~~~

Unique constraint chống hai consumer cùng xử lý duplicate event ID. Nếu event 12 đến trước 11, inbox không nên đánh dấu event 12 hoàn tất khi nó chưa được áp dụng; cần trạng thái PENDING/BUFFERED hoặc transaction rollback để retry tùy chiến lược.

### 11.1. Duplicate và out-of-order là hai vấn đề khác nhau

- Duplicate: cùng logical event xuất hiện nhiều lần.
- Out-of-order: các logical events khác nhau tới sai thứ tự.
- Stale command: caller gửi lệnh dựa trên state version cũ.
- Replay: event lịch sử được phát lại có chủ đích.
- Concurrent commands: nhiều thao tác mới cạnh tranh cùng aggregate.

Deduplication không tự sửa ordering; sequence check không tự ngăn duplicate side effect nếu cùng version xử lý lặp.

## 12. Xử lý event đến sai thứ tự

Consumer đang lưu state version 5:

- Nhận version 5 lần nữa: duplicate/stale, bỏ qua hoặc trả idempotent result.
- Nhận version 4: cũ, không áp dụng state regression.
- Nhận version 6: kế tiếp, có thể áp dụng.
- Nhận version 8: gap 7; xử lý theo semantics của event.

### 12.1. Ba chiến lược

**Reject and retry:** không nhận event có gap; rollback/không ack để retry sau khi event trước được xử lý. Cần tránh poison message chặn partition mãi.

**Buffer by aggregate:** lưu event tới sớm vào bảng pending, chờ version còn thiếu; worker áp dụng khi đủ. Cần TTL, bounded storage, alert và reconciliation nếu gap không bao giờ đến.

**Fetch authoritative snapshot:** query owner lấy state mới nhất, rồi đồng bộ consumer projection. Cách này phù hợp nếu consumer cần current state, nhưng có thể bỏ mất side effects cần phát theo từng event. Phải phân biệt projection rebuild với business command processing.

### 12.2. Snapshot và delta

- OrderStateChanged có thể là full snapshot state=PAID, version=6.
- PaymentCapturedAmountIncreased có thể là delta +10000, version=6.

Với snapshot, có thể áp dụng version mới hơn nếu contract cho phép bỏ qua trung gian. Với delta, bỏ version 5 có thể làm số tiền sai. Event contract phải mô tả rõ loại dữ liệu.

### 12.3. DLQ không được làm mất invariant

Đưa event vào DLQ có thể giải phóng partition, nhưng nếu event đó là bước bắt buộc trong aggregate sequence thì events sau có thể không an toàn để tiếp tục. Cần chính sách per-key pause, quarantine aggregate, manual repair hoặc snapshot reconciliation. Đừng chỉ bỏ qua mọi poison message.

## 13. HTTP requests cũng có thể bị đảo thứ tự

Client có thể gửi hai requests gần đồng thời qua HTTP/2 multiplexing, gateway có thể retry, hai replicas xử lý khác nhau và database commit theo lịch riêng.

Ví dụ người dùng:
1. Đổi địa chỉ giao hàng.
2. Đặt đơn dùng địa chỉ mới.

Nếu hai request chạy song song, CreateOrder có thể đọc địa chỉ cũ dù người dùng bấm sau. Không thể dựa vào thứ tự click hoặc packet đến để bảo đảm business semantics.

### 13.1. Cách diễn đạt thứ tự trong contract

- Client chờ response của bước trước rồi mới gửi bước sau nếu dependency rõ.
- Dùng expectedVersion/If-Match cho cập nhật resource.
- Gửi một command có snapshot/reference version đã được xác nhận.
- Đưa chuỗi thao tác vào coordinator/queue theo aggregate key.
- Dùng transaction ở owner khi thay đổi cùng resource/database.

### 13.2. Optimistic concurrency với ETag

~~~http
PATCH /v1/accounts/acct-11
If-Match: "version-7"
Content-Type: application/json

{"shippingAddressId":"addr-22"}
~~~

Nếu version hiện tại đã là 8, server có thể trả 412 Precondition Failed. Caller đọc lại resource và quyết định thao tác tiếp theo, thay vì ghi đè thay đổi mới hơn.

### 13.3. Idempotency không đồng nghĩa ordering

Idempotency bảo đảm lặp cùng operation không tạo side effect lặp. Nó không quyết định A phải xảy ra trước B. Hai request với hai keys khác nhau vẫn có thể cạnh tranh; cần version/precondition/queue hoặc state machine.

## 14. Causal order giữa nhiều service

Một workflow:

~~~text
OrderCreated
    |
    v
PaymentRequested
    |
    v
PaymentAuthorized
    |
    v
InventoryConfirmRequested
    |
    v
OrderConfirmed
~~~

Mỗi bước sinh ra vì kết quả bước trước. causationId có thể ghi event/command trực tiếp gây ra event hiện tại; correlationId nối messages cùng workflow. Chúng hỗ trợ trace causal chain nhưng không tự enforce order.

### 14.1. Saga coordinator giữ workflow sequence

Coordinator lưu state machine và chỉ phát command kế tiếp khi precondition thỏa. Nếu worker restart, nó đọc state bền vững và tiếp tục. Không dựa vào thứ tự message tình cờ để điều phối.

### 14.2. Choreography vẫn cần state guards

Trong choreography, nhiều service phản ứng với event. Nếu hai event cùng lúc kích hoạt các bước khác nhau, owner phải có state transition guard. Event correlation không thay thế atomicity.

### 14.3. Cross-service global order thường không cần

Order A và Order B độc lập không cần một thứ tự toàn cục. Cần giữ order trong từng orderId và các invariant resource tương ứng. Nếu campaign quota là chung, Promotion Service bảo vệ quota đó tại owner; không cần sắp mọi event toàn hệ thống vào một stream.

## 15. Khi nào cần total/global ordering?

Global ordering chỉ nên dùng khi domain thực sự cần một trình tự duy nhất trong phạm vi cụ thể:

- Ledger cần sequence authority cho một account hoặc ledger scope.
- Một resource duy nhất có mọi lệnh cạnh tranh.
- Migration protocol cần barrier/epoch.
- Global sequence phục vụ audit hoặc snapshot consistency.
- Replicated state machine cần các nodes áp dụng cùng command log.

Ngay cả khi cần, thường phạm vi có thể thu nhỏ: một account ledger, một resource, một partition hoặc một shard thay vì toàn công ty.

### 15.1. Cơ chế tạo global order

- Sequencer/leader cấp số thứ tự.
- Consensus-backed replicated log.
- Database transaction/sequence với serialization ở scope xác định.
- Single-writer partition/actor cho resource.
- Coordinator dùng lease có fencing khi owner kiểm token.

Mỗi cách có trade-off. Single leader có bottleneck/failover; database sequence cấp ID tăng dần nhưng không tự chứng minh commit order; consensus có chi phí network/quorum và có thể unavailable khi mất quorum.

### 15.2. Global total order đắt ở đâu?

- Mọi writers phải phối hợp với cùng authority.
- Contention và queueing tăng khi throughput cao.
- Leader/quorum/network trở thành dependency critical.
- Failover cần fencing/epoch để leader cũ không tiếp tục ghi.
- Độ trễ tăng do coordination.
- Một partition/resource hot có thể giới hạn toàn luồng.

Nếu chỉ cần per-account order, global sequencer cho mọi account là lãng phí.

### 15.3. Serializable transaction không phải global order toàn hệ thống

Isolation SERIALIZABLE có thể bảo vệ transaction trong một database theo semantics của engine. Nó không tự tạo total order giữa nhiều database/service độc lập. Phải phân biệt phạm vi transaction và phạm vi business invariant.

## 16. Invariant nhiều key: giới hạn của per-key order

Campaign có tổng quota 100 voucher. Nếu partition theo customerId, từng khách có thứ tự riêng nhưng 200 khách vẫn có thể cùng thấy quota còn và xin cấp:

~~~text
customer-A lane ─┐
customer-B lane ─┼──> Promotion global quota = 100
customer-C lane ─┘
~~~

Per-customer order không bảo vệ global quota. Owner cần atomic quota decrement, reservation pool/escrow hoặc phân bổ quota theo shard với giới hạn rõ.

### 16.1. Inventory multi-SKU

Một order cần SKU-A và SKU-B. Nếu hai keys ở partition khác nhau, không có atomic cross-partition transaction mặc định. Có thể:
- Inventory owner dùng local DB transaction nếu cả hai records cùng database.
- Dùng reservation group và Saga nếu resources/owners tách biệt.
- Áp dụng thứ tự khóa cố định để giảm deadlock trong cùng datastore.
- Dùng escrow/allocation model cấp trước quota cho từng shard.
- Chấp nhận partial holds và compensation có kiểm soát.

### 16.2. Account transfer

Chuyển tiền từ account A sang B cần bảo vệ số dư cả hai. Per-account ordering giúp tuần tự từng account nhưng transfer là thao tác nhiều key. Nếu cùng ledger owner, transaction atomic/serializable có thể bảo vệ; nếu owners tách biệt, cần transfer state machine với debit/credit idempotent, hold và reconciliation.

### 16.3. Cross-key coordination không nhất thiết là global ordering

Có thể phối hợp chỉ những keys tham gia cùng một operation. Không cần đưa accounts hoặc SKUs không liên quan vào một global queue.

## 17. Partition key và hot-key trade-offs

| Key | Lợi ích | Rủi ro |
| --- | --- | --- |
| orderId | Per-order order tự nhiên, song song giữa orders | Một order có event lớn thành hot key |
| customerId | Thứ tự theo khách | Khách lớn tạo hotspot; không bảo vệ inventory global |
| tenantId | Dễ áp dụng tenant-wide sequence/quota | Tenant lớn làm một partition nóng |
| sku | Cùng SKU vào một lane | SKU phổ biến hot; nhiều kho cần warehouseId |
| accountId | Ledger/account events tuần tự | Transfer nhiều account cần coordination |
| Random key | Phân phối đều | Không giữ business ordering |

### 17.1. Hot key là giới hạn của serialization

Nếu cùng một key cần strictly sequential processing, throughput của key đó bị giới hạn bởi khả năng xử lý tuần tự. Tăng partitions không làm một key duy nhất tự động song song mà vẫn giữ strict order.

Cần tối ưu transaction, gộp event, batch, partition theo sub-resource nếu invariant cho phép hoặc thay đổi mô hình nghiệp vụ. Không tách key tùy tiện chỉ để tăng throughput nếu làm mất invariant.

### 17.2. Composite key

sku + warehouseId giúp tách cùng SKU ở các kho độc lập. Nhưng nếu tồn kho được chia sẻ toàn vùng, key đó có thể quá hẹp. Key phải phản ánh chính xác resource owner và nơi invariant được thực thi.

### 17.3. Partition expansion và migration

Thay partition count/partitioner có thể remap key. Với ordering nghiêm ngặt, cần:
1. Xác định keys nào phải giữ thứ tự.
2. Chọn thời điểm cutover và drain producer cũ nếu cần.
3. Drain partitions cũ tới offset barrier.
4. Tạo topic/version mới hoặc mapping ổn định.
5. Đảm bảo một aggregate không bị xử lý đồng thời ở đường cũ và mới.
6. Dùng aggregateVersion để reject stale events.
7. Theo dõi gap, duplicate, reordering và consumer lag.
8. Có replay/reconciliation và rollback plan.

Không dựa vào hash key ổn định nếu số partitions/partitioner có thể đổi.

## 18. Sequence, version, epoch và fencing token

| Token | Mục đích |
| --- | --- |
| Aggregate version | Thứ tự các lần thay đổi của một aggregate |
| Event sequence | Thứ tự event trong stream/aggregate |
| Partition offset | Vị trí record trong một partition broker |
| Epoch/generation | Phân biệt các thế hệ owner/leader/lease |
| Fencing token | Chặn writer cũ sau khi quyền chuyển owner mới |
| Idempotency key | Nhận diện cùng logical operation |
| Correlation ID | Nối messages cùng workflow |
| Causation ID | Ghi event/command trực tiếp gây ra event hiện tại |

Không thay thế lẫn nhau. Offset 100 của partition 0 không so được với offset 100 của partition 1 để suy ra global order. Idempotency key không phải sequence. Correlation ID không chứng minh causality nếu không có quy tắc producer.

### 18.1. Fencing khi lease/leader đổi

~~~text
Leader A epoch=7
A bị network pause
Leader B được bầu epoch=8
Storage chấp nhận epoch=8
A tỉnh lại gửi write epoch=7
Storage từ chối write cũ
~~~

Lease expiry chỉ cho biết quyền A đã hết theo policy. Nếu receiver không kiểm fencing token, A vẫn có thể gây side effect sau khi lease hết. Token phải được kiểm tại storage/receiver có quyền ghi.

### 18.2. Epoch và sequence reset

Không reset aggregate version về 1 khi resource được tái sử dụng nếu consumer vẫn có thể thấy event cũ cùng aggregateId. Có thể dùng generation mới, ID mới hoặc epoch + sequence để phân biệt.

## 19. Retry, DLQ và thứ tự

Giả sử cùng order có events v1, v2, v3. v1 tạm lỗi và được retry; v2/v3 có thể tiếp tục không?

- Nếu consumer xử lý delta cần thứ tự, tiếp tục v2/v3 có thể sai.
- Nếu event là snapshot và version guard bảo vệ state, có thể áp dụng v3 rồi bỏ stale v1/v2 theo contract.
- Nếu v1 là payment side effect bắt buộc, bỏ qua nó không hợp lệ.
- Nếu v1 poison message, cần quarantine aggregate hoặc repair thay vì block toàn topic vô hạn.

### 19.1. Retry topic có thể đảo thứ tự

Đưa message lỗi sang retry topic với delay trong khi message sau tiếp tục ở main topic có thể làm event sau được xử lý trước. Cần xác định:
- Per-key pause/blocking.
- Retry partition giữ cùng key.
- Version check + buffer.
- Retry toàn aggregate từ state.
- DLQ/manual repair và cách resume.

### 19.2. DLQ không phải “bỏ qua cho xong”

Một event vào DLQ có thể tạo sequence gap. Cần alert, owner, replay tool, idempotency và kiểm tra side effect đã commit chưa. Không tự động replay DLQ bằng key mới hoặc sửa payload mà không audit.

### 19.3. Consumer crash sau side effect

Nếu consumer gọi Payment provider thành công rồi crash trước khi ack, record được giao lại. Consumer phải giữ operationId/idempotency key để provider nhận ra cùng logical payment, không tạo charge mới.

## 20. Một số lựa chọn triển khai

### 20.1. Actor/single-writer per aggregate

Mỗi aggregate được xử lý bởi một actor/mailbox tại một thời điểm:

~~~text
order-101 mailbox: cmd1 → cmd2 → cmd3
order-102 mailbox: cmdA → cmdB
~~~

Ưu điểm là mô hình dễ suy luận theo key; đánh đổi là lifecycle, persistence, rebalancing, hot keys và failover. Khi actor migrate, cần fencing/epoch để writer cũ không tiếp tục tác động.

### 20.2. Partitioned queue

Đưa messages cùng key vào một partition. Consumer xử lý tuần tự partition hoặc đảm bảo per-key sequential execution. Phù hợp event streaming; vẫn cần version/deduplication và xử lý partition rebalance.

### 20.3. Database optimistic concurrency

Mỗi command gửi expectedVersion; UPDATE có điều kiện. Phù hợp resource state trong một database owner, phát hiện stale writes. Caller xử lý conflict bằng refresh/retry theo semantics.

### 20.4. Pessimistic locking

SELECT FOR UPDATE/row lock tuần tự hóa transaction cùng resource. Dùng cho critical section ngắn và database phù hợp. Cần lock order, timeout, deadlock handling và transaction ngắn.

### 20.5. Per-key sequencer

Một thành phần cấp sequence cho mỗi aggregate/resource. Có thể dùng database row, counter/transaction hoặc actor. Sequencer phải là authority và xử lý failover; sequence cấp trước nhưng transaction sau rollback cần quy tắc gap.

### 20.6. Escrow/quota partitioning

Khi cần quota toàn cục nhưng muốn scale, owner có thể phân bổ quota cho shard:

~~~text
Global quota = 100
  shard A allowance = 30
  shard B allowance = 30
  shard C allowance = 40
~~~

Mỗi shard xử lý local reservations trong allowance. Không vượt global quota nếu allocation/rebalancing đúng; nhưng quota tạm chưa dùng ở A có thể chưa khả dụng ở B đến khi chuyển. Đây là trade-off availability/efficiency.

## 21. SQL: bảo vệ version và state transition

Giả sử Order hiện version 7, status=PAID. Một command muốn chuyển sang PACKING:

~~~sql
UPDATE orders
SET status = 'PACKING',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :order_id
  AND status = 'PAID'
  AND version = 7;
~~~

Nếu update thành công, transition hợp lệ. Nếu không, caller đọc lại state/version để phân biệt:
- Đã PACKING bởi request trùng: trả kết quả idempotent.
- Đã CANCELLED: không được đóng gói.
- Version tăng do transition khác: conflict/stale command.
- Order không tồn tại hoặc caller không có quyền: xử lý theo contract.

### 21.1. Event/outbox cùng transaction

~~~sql
BEGIN;

UPDATE orders
SET status = 'PACKING',
    version = version + 1
WHERE order_id = :order_id
  AND status = 'PAID'
  AND version = :expected_version;

-- Chỉ khi affected rows = 1:
INSERT INTO outbox_events(
    event_id, aggregate_id, aggregate_version,
    event_type, payload, created_at
) VALUES (
    :event_id, :order_id, :new_version,
    'PackingStarted', :payload, CURRENT_TIMESTAMP
);

COMMIT;
~~~

Application phải kiểm affected rows và chỉ insert outbox khi transition thành công; nếu thất bại thì rollback hoặc trả conflict theo contract.

### 21.2. Sequence ID không phải commit order mặc định

Database sequence có thể cấp ID 100 cho transaction A rồi 101 cho B; B commit trước A. Sequence tăng không tự phản ánh commit order. Nếu cần aggregate order, tăng version trong cùng aggregate transaction/lock.

## 22. Java/Spring: xử lý version và stale events

DTO event:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    long aggregateVersion,
    String eventType,
    Instant occurredAt
) {}
~~~

Consumer kiểm version (pseudo-code):

~~~java
@Transactional
public ApplyResult apply(OrderEvent event) {
    if (inboxRepository.existsByEventId(event.eventId())) {
        return ApplyResult.DUPLICATE;
    }

    OrderProjection current =
        projectionRepository.lockByOrderId(event.orderId());

    if (event.aggregateVersion() <= current.version()) {
        inboxRepository.record(event);
        return ApplyResult.STALE;
    }

    if (event.aggregateVersion() != current.version() + 1) {
        return ApplyResult.GAP;
    }

    projectionRepository.apply(event);
    inboxRepository.record(event);
    return ApplyResult.APPLIED;
}
~~~

Đây là pseudo-code. Khi trả GAP, transaction cần rollback hoặc event được lưu pending rõ ràng; không ghi inbox “processed” rồi bỏ event mất. Duplicate check và projection update nên nằm cùng transaction để crash không tạo state nửa vời.

### 22.1. Nếu event là snapshot

Nếu contract xác định event là full state snapshot, consumer có thể dùng:

~~~sql
UPDATE order_projection
SET status = :status,
    version = :incoming_version
WHERE order_id = :id
  AND version < :incoming_version;
~~~

Điều này bỏ qua version cũ và cập nhật lên version mới hơn. Chỉ dùng khi event snapshot đủ dữ liệu để thay state; không dùng cho delta hoặc side effects cần thực hiện từng bước.

### 22.2. Spring Kafka: key theo aggregate

~~~java
kafkaTemplate.send(
    "order-events",
    event.orderId(),
    event
);
~~~

Consumer listener:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "fulfillment-projection"
)
public void consume(OrderEvent event) {
    orderEventHandler.apply(event);
}
~~~

Cấu hình thực tế phải xác định serializer/deserializer, partition count, ack/commit mode, concurrency, error handler, retry/DLT và transaction semantics. Chỉ set key và dùng @KafkaListener chưa bảo đảm consumer side effects hoàn tất theo thứ tự nếu handler tự dispatch bất đồng bộ.

### 22.3. Chạy song song giữa keys

Một hướng là giới hạn concurrency theo partitions và tuần tự xử lý records trong từng partition. Nếu muốn nhiều keys cùng partition chạy song song, cần keyed executor/partitioned processing và version checks. Cân nhắc rebalance, in-flight tasks và commit offset trước khi tối ưu.

## 23. Thay đổi partitioning và contract ordering

Khi tăng partition count, đổi key schema hoặc đổi topic, cần coi đó là thay đổi contract vận hành:

1. Xác định keys nào phải giữ thứ tự.
2. Chọn thời điểm cutover và dừng/giới hạn producer cũ nếu cần.
3. Drain partitions cũ tới offset barrier.
4. Tạo topic/version mới hoặc mapping ổn định.
5. Đảm bảo mỗi aggregate không bị xử lý song song ở cả đường cũ và mới.
6. Dùng aggregateVersion để reject stale events.
7. Theo dõi gap, duplicate, reordering và consumer lag.
8. Có replay/reconciliation và rollback plan.

Không thể đơn giản tăng partitions rồi giả định broker di chuyển record cũ sang partition mới.

## 24. Global ordering: khi nào xứng đáng trả chi phí?

Một số nghiệp vụ thật sự cần thứ tự chung trong phạm vi nhỏ: ledger của một account, tài nguyên duy nhất có mọi lệnh cạnh tranh, một stream audit có sequence authority hoặc replicated state machine.

Hãy giới hạn scope càng nhỏ càng tốt. **Một global sequence cho tất cả orders** thường không cần nếu orders độc lập.

### 24.1. Sequencer/leader

Một leader cấp monotonic sequence. Cần:
- Leader election và epoch.
- Fencing để leader cũ không ghi.
- Durable sequence state.
- Behavior khi quorum/leader unavailable.
- Capacity/latency measurement.

Nếu sequencer unavailable, có thể phải chờ; nếu writers tự cấp sequence, global uniqueness/order có thể mất.

### 24.2. Consensus log

Một replicated consensus log có thể đưa commands vào một thứ tự được thống nhất trong phạm vi cluster. Tuy nhiên quorum/network coordination tăng latency và khi không đủ quorum, hệ thống có thể không nhận writes. Nó không tự tạo transaction chung với service ngoài cluster.

### 24.3. Serializable transaction

Một database có SERIALIZABLE isolation có thể phát hiện/điều chỉnh các transaction xung đột trong database đó. Phạm vi vẫn là database/transaction engine cụ thể; không bao phủ Payment API hoặc database của service khác.

### 24.4. Không có global order mà vẫn đúng

Nếu invariant có thể bảo vệ tại owner:
- Per-order state dùng order version.
- Per-SKU stock dùng inventory transaction.
- Per-account balance dùng ledger transaction.
- Cross-service checkout dùng Saga.

thì không cần một stream toàn cục.

## 25. Bài tập: xác định key và guarantee

| Tình huống | Key có thể phù hợp | Guarantee cần cân nhắc |
| --- | --- | --- |
| Cập nhật trạng thái order | orderId | Per-aggregate order + version |
| Trừ tiền cùng account | accountId | Per-account serialization/ledger invariant |
| Giữ một ghế | seatId | Atomic single-resource transition |
| Giữ stock trong một kho | sku + warehouseId | Per-resource atomic capacity |
| Giới hạn coupon toàn campaign | campaignId | Shared quota/atomic decrement |
| Notification analytics | Không cần business key hoặc key phân tải | Unordered/at-least-once + dedupe |
| Cập nhật profile một khách | customerId | Per-customer version |
| Chuyển tiền A → B | transferId + hai account owners | Multi-key transaction/workflow |

Key cuối cùng phải theo owner và invariant thực tế.

## 26. Kiểm thử ordering và concurrency

### 26.1. Cùng key, hai command

~~~text
Given:
  order-101 version=5, state=PAID

When:
  Command A: StartPacking(expectedVersion=5)
  Command B: Cancel(expectedVersion=5)
  chạy đồng thời

Then:
  Chỉ một transition hợp lệ thắng theo state machine.
  Command còn lại nhận conflict/terminal state rõ.
  Không có hai side effects không tương thích.
~~~

### 26.2. Khác key, có thể song song

~~~text
Given:
  order-101 và order-102 độc lập

When:
  consumer nhận event của cả hai

Then:
  hai keys có thể xử lý song song
  mỗi aggregate vẫn tăng version tuần tự
~~~

### 26.3. Event đảo thứ tự

Projection version 8 nhận version 10 rồi version 9. Kiểm tra:
- Version 10 không bị áp dụng sai nếu là delta.
- Gap được buffer/retry/repair.
- Version 9 tới sau không ghi lùi state.
- Alert phát khi gap kéo dài.
- Replay không tạo side effect trùng.

### 26.4. Partition rebalance

- Consumer A đang xử lý record v5 thì mất ownership.
- Consumer B nhận partition và bắt đầu v6.
- A vẫn còn task async chưa dừng.
- Test fencing/version checks chặn A ghi sau B.
- Offset commit không bỏ sót record.

### 26.5. Outbox relay song song

Hai relay workers đọc version 4 và 5 của cùng order. Ép version 5 publish trước. Xác minh consumer phát hiện gap và không áp dụng sai; hoặc relay policy giữ publish order theo aggregate.

### 26.6. Partition expansion

Phát events cùng key trước và sau khi tăng partition count. Kiểm tra migration strategy bảo toàn order/sequence, không để consumer cũ/mới ghi đè nhau.

### 26.7. Retry và duplicate

- Cùng eventId gửi hai lần.
- Hai event khác eventId nhưng cùng aggregateVersion.
- Command retry với cùng idempotency key.
- Retry topic trả event cũ sau event mới.
- DLQ replay sau khi aggregate đã chuyển terminal.

### 26.8. Global quota

Hai trăm customer keys đồng thời xin 100 coupon. Per-customer ordering không đủ. Kiểm atomic quota owner/escrow allocation bảo đảm không vượt 100.

### 26.9. Assertions

~~~text
aggregate.version không giảm
không áp dụng delta nếu thiếu sequence trước
một eventId không tạo side effect hai lần
cùng key không có hai terminal transitions xung đột
global invariant vẫn đúng khi nhiều keys chạy song song
outbox event version phản ánh commit của aggregate
~~~

## 27. Observability cho ordering

| Metric | Điều cần phát hiện |
| --- | --- |
| aggregate_version_gap | Consumer thiếu version |
| stale_event_count | Event cũ đến sau |
| duplicate_event_count | Message/event xử lý lặp |
| per_key_queue_depth | Hot key hoặc backlog theo aggregate |
| partition_lag | Consumer chậm ở partition |
| processing_out_of_order | Completion order sai so với sequence |
| dlq_count / dlq_age | Event lỗi bị giữ lâu |
| outbox_publish_lag | Event chưa publish đúng hạn |
| rebalance_count | Partition ownership biến động |
| optimistic_lock_conflict | Concurrent state transitions |
| global_quota_conflict | Nhiều keys cạnh tranh resource chung |
| hot_key_processing_time | Một key giới hạn throughput |
| reconciliation_backlog | Sequence gap/workflow chưa khôi phục |

### 27.1. Trace fields

Có thể đưa vào span/log:
- aggregateId (ẩn danh hoặc hạn chế cardinality).
- aggregateVersion/sequence.
- eventId, correlationId, causationId.
- topic/partition/offset.
- consumer instance/version.
- retry count, processing attempt.
- state before/after.

Không dùng từng aggregateId làm metric label có cardinality vô hạn. Log/tracing phải tuân chính sách PII và secret.

### 27.2. Alert theo business impact

Một version gap kéo dài trên Order có thể ảnh hưởng fulfillment; gap trên telemetry không quan trọng tương tự. Alert dựa trên owner, loại event, age và business impact, không chỉ tổng số gap.

## 28. Phản mẫu thường gặp

**“Kafka giữ thứ tự nên toàn hệ thống đã ordered.”**  
Sai. Kafka chỉ có thứ tự trong partition; consumer async, retries và side effects có thể đảo.

**“Sắp xếp theo timestamp là đủ.”**  
Sai. Clock skew, commit delay và duplicate timestamp làm timestamp không chứng minh causal/commit order.

**“Dùng customerId làm key thì bảo vệ được stock.”**  
Sai. Hai customer khác nhau vẫn cạnh tranh cùng SKU. Key phải theo invariant resource.

**“Tăng partition count luôn tăng throughput mà không có ảnh hưởng.”**  
Sai. Key mapping có thể thay đổi, gây hai lanes cho cùng aggregate qua thời điểm cutover.

**“Consumer concurrency=10 vẫn giữ per-key order tự nhiên.”**  
Không nếu code dispatch records cùng key đồng thời. Cần per-key serialization hoặc version/CAS.

**“Outbox có createdAt nên relay chỉ cần ORDER BY createdAt.”**  
Chưa đủ khi nhiều workers claim/publish đồng thời. Dùng aggregate sequence và relay policy.

**“Idempotency bảo đảm command A chạy trước B.”**  
Không. Idempotency chỉ xử lý lặp cùng operation; ordering cần sequence/precondition.

**“Global sequence database tự động bằng commit order.”**  
Không. Sequence có thể được cấp trước và transaction commit sau theo thứ tự khác.

**“Per-key ordering bảo vệ mọi invariant.”**  
Không khi invariant liên quan nhiều keys, campaign quota hoặc cross-resource transfer.

**“Đưa event lỗi vào DLQ rồi tiếp tục mọi event sau.”**  
Có thể làm consumer state thiếu transition bắt buộc. Cần gap/quarantine/replay policy.

**“Event đến muộn cứ ghi đè vì nó mới được nhận.”**  
Sai. Arrival time không phải business version; có thể làm state regression.

**“Có aggregateVersion là không cần idempotency.”**  
Không. Duplicate side effects cùng version vẫn có thể xảy ra nếu handler không dedupe.

**“Một global queue là cách đơn giản nhất.”**  
Nó có thể trở thành bottleneck và single point of coordination. Chỉ dùng nếu global order thực sự là requirement.

## 29. Bài tập thực hành

### Bài 1 — Chọn key cho đơn hàng
OrderCreated, PaymentCaptured, CancelRequested và ShipmentStarted đều mang orderId. Xác định key và state transition để một đơn không vừa bị hủy vừa được giao.

### Bài 2 — Partition key cho tồn kho
Inventory có nhiều SKU và warehouse. Chọn key, phân tích SKU hot, giải thích vì sao customerId không bảo vệ stock.

### Bài 3 — Event version gap
Projection version 8 nhận version 10 trước version 9. Viết chiến lược cho event delta và snapshot; định nghĩa timeout, DLQ và reconciliation.

### Bài 4 — Consumer concurrency
Kafka partition có offsets 100, 101, 102 cùng orderId. Consumer poll tuần tự nhưng dispatch executor; 101 hoàn thành trước 100. Sửa thiết kế và kiểm offset commit.

### Bài 5 — Global quota
Campaign quota 1.000, partition theo customerId. Thiết kế atomic quota decrement hoặc escrow allocation và nêu trade-off khi một shard hết allowance.

### Bài 6 — Tăng partitions
Topic từ 12 lên 24 partitions. Mô tả rủi ro remap key và kế hoạch cutover/drain/version validation.

### Bài 7 — Timestamp và causality
Service A ghi occurredAt=10:00:01.100; service B ghi event phụ thuộc occurredAt=10:00:00.900 do clock lệch. Chỉ ra vì sao sort timestamp sai và cách dùng causationId/aggregateVersion.

### Bài 8 — Outbox relay
Hai workers publish aggregate version 4 và 5 ngược thứ tự. Chọn relay serialization, partition key và consumer gap handling.

### Bài 9 — Transfer nhiều account
Một transfer cần debit A và credit B; mỗi account có per-key ordering. Thiết kế transfer state machine và xử lý partial success/retry/reconciliation.

### Bài 10 — Đánh giá global ordering
Một sản phẩm muốn mọi event trong toàn công ty có một sequence tăng dần. Xác định requirement nào thực sự cần total order, đề xuất scope nhỏ hơn và tính chi phí sequencer.

## 30. Checklist trước khi công bố guarantee ordering

### Business scope
- [ ] Đã nêu rõ ordering cần theo business key nào.
- [ ] Key phản ánh resource/invariant owner thực sự.
- [ ] Đã nhận diện invariant liên quan nhiều keys.
- [ ] Không yêu cầu global total order cho aggregate độc lập.
- [ ] Causal dependencies và state machine được mô tả.

### Producer/storage
- [ ] Owner cấp aggregateVersion/sequence trong transaction.
- [ ] State transition dùng expected state/version hoặc atomic constraint.
- [ ] Outbox event cùng commit với state.
- [ ] Relay không publish đảo version cùng aggregate, hoặc consumer có gap handling.
- [ ] Partition key ổn định và có plan khi thay partition count.

### Consumer
- [ ] Cùng key không chạy side effects đồng thời trái contract.
- [ ] Duplicate event được dedupe.
- [ ] Stale version bị bỏ qua an toàn.
- [ ] Version gap được buffer/retry/snapshot/reconcile đúng loại event.
- [ ] Offset/ack chỉ commit theo semantics xử lý.
- [ ] Retry/DLQ/replay không phá sequence.
- [ ] Rebalance/worker cũ có fencing/version protection khi cần.

### Global invariants
- [ ] Campaign quota, stock và multi-account operations có owner/atomic coordination riêng.
- [ ] Không dùng per-key order để tuyên bố global guarantee.
- [ ] Nếu dùng sequencer/consensus, đã đánh giá availability, latency và failover.
- [ ] Có epoch/fencing nếu leader/lease có thể thay.
- [ ] Có reconciliation khi nhiều service không cùng transaction.

### Operations
- [ ] Metrics có gap, stale, duplicate, hot key, partition lag, outbox lag.
- [ ] Alert dựa trên age và business impact.
- [ ] Load tests gồm hot key và cross-key contention.
- [ ] Partition migration/replay có runbook.
- [ ] Contract công bố rõ phạm vi, duplicate, ordering và version semantics.

## 31. Mẫu ADR

~~~markdown
# ADR: Business-Key Ordering Strategy

## Context
- Aggregate/resource:
- Business invariant:
- Operations/events cạnh tranh:
- Throughput and hot-key profile:
- Các service/queues/database tham gia:

## Ordering requirement
- Key:
- Scope: per entity / partition / causal / global
- Ordering point: accepted / committed / published / processed
- Duplicate delivery policy:
- Out-of-order/gap policy:
- Snapshot vs delta event semantics:

## Decision
- Partition key:
- Aggregate version/sequence:
- Producer/outbox serialization:
- Consumer concurrency:
- Inbox/deduplication:
- Retry/DLQ/replay:
- Optimistic/pessimistic concurrency:
- Cross-key coordination:
- Fencing/epoch:
- Global sequencer (nếu thật sự cần):

## Alternatives
- Single global queue:
- Per-key partitions:
- Actor/single writer:
- Database serialization:
- Materialized state/version checks:

## Consequences
- Throughput:
- Tail latency:
- Hot-key risk:
- Availability/failover:
- Operational complexity:
- Reconciliation requirements:

## Validation
- Concurrent same-key commands:
- Different-key parallelism:
- Duplicate/out-of-order events:
- Rebalance and partition expansion:
- Global quota/cross-key invariants:
- DLQ/replay:
- Metrics and alerts:
~~~

## 32. Tổng kết

**Ordering phải được định nghĩa theo phạm vi nghiệp vụ cần bảo vệ.** Nhiều aggregate độc lập có thể chạy song song; các thao tác cùng aggregate hoặc cùng resource cần một thứ tự có thể kiểm chứng. Broker partition, aggregate version, database transaction, causal metadata và global sequencer cung cấp các lớp bảo đảm khác nhau, không thể đánh đồng.

Các nguyên tắc cần nhớ:

1. **Chọn business key theo invariant.** orderId bảo vệ state của một đơn; sku/warehouse bảo vệ stock; campaignId bảo vệ quota chung.
2. **Phân biệt per-key, per-partition, causal và global order.** Không quảng cáo guarantee rộng hơn cơ chế thực tế.
3. **Dùng version/sequence ở owner.** Timestamp và arrival order không chứng minh commit order.
4. **Broker order chưa phải end-to-end order.** Consumer concurrency, retries, DLQ, rebalance và side effects có thể làm đảo kết quả.
5. **Idempotency và ordering giải quyết hai bài toán khác nhau.** Cần cả hai khi có duplicate và concurrent commands.
6. **Per-key order không bảo vệ invariant nhiều key.** Quota chung, multi-SKU và transfer cần transaction/coordination ở owner.
7. **Global order có chi phí.** Chỉ dùng trong scope thực sự cần, với sequencer/consensus/fencing và kế hoạch failover.
8. **Kiểm thử cả lúc bình thường lẫn khi lỗi.** Duplicate, gap, hot key, partition expansion, consumer crash và replay là một phần contract.

Câu hỏi review cuối cùng: **“Thứ tự nào thực sự cần thiết để giữ invariant, ai có quyền cấp sequence, và điều gì xảy ra khi một event cũ đến sau event mới?”** Một thiết kế tốt trả lời được ba câu hỏi đó mà vẫn cho phép các business keys độc lập xử lý song song.
