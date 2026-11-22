# Phân vùng, khóa thông điệp và phạm vi bảo đảm thứ tự trong giao tiếp bất đồng bộ Microservices

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Giao tiếp bất đồng bộ.  
> **Mục tiêu:** Hiểu cách partition và message key quyết định phạm vi thứ tự; chọn key theo bất biến nghiệp vụ; bảo vệ state trước concurrency, retry, duplicate, rebalance và replay; thiết kế hệ thống vừa xử lý song song vừa giữ được những trật tự thật sự quan trọng.

## 1. Vì sao thứ tự sự kiện không phải chuyện riêng của broker?

Trong Microservices, một hành trình nghiệp vụ thường tạo nhiều sự kiện theo thời gian:

~~~text
OrderCreated(orderId=O-101, version=1)
OrderSubmitted(orderId=O-101, version=2)
PaymentAuthorized(orderId=O-101, version=3)
OrderCancelled(orderId=O-101, version=4)
~~~

Nếu một consumer áp dụng sự kiện Cancelled trước rồi ghi đè bằng Submitted đến trễ, trạng thái cuối sai. Nếu service gửi email xác nhận sau khi đơn đã hủy, người dùng nhận thông tin gây nhầm lẫn. Nếu consumer tài chính xử lý debit hai lần do redelivery, hậu quả còn nghiêm trọng hơn.

Cùng lúc, hệ thống cần xử lý hàng nghìn đơn độc lập song song. Ép toàn bộ sự kiện của mọi đơn chạy tuần tự trong một luồng có thể bảo vệ một dạng thứ tự, nhưng làm throughput, thời gian chờ và availability xấu đi.

Vì vậy, câu hỏi đầu tiên là:

**Những message nào phải được xử lý theo thứ tự với nhau để bảo vệ tính đúng đắn, và những message nào có thể xử lý song song?**

Các vấn đề phải xét xuyên suốt:

1. Producer có phát sự kiện đúng thứ tự nghiệp vụ không?
2. Message key có đưa sự kiện cùng đối tượng vào cùng phạm vi sắp thứ tự không?
3. Broker cung cấp thứ tự ở phạm vi partition, queue hay message group?
4. Consumer nhận theo thứ tự nhưng có commit kết quả theo thứ tự không?
5. Retry hoặc DLQ có cho phép event đến sau vượt event lỗi trước đó không?
6. Rebalance, crash, replay và migration key có làm event cũ xuất hiện lại không?
7. State store có version và idempotency để chống thay đổi lỗi thời không?

Bảo đảm thứ tự phải được định nghĩa bằng **kết quả nghiệp vụ quan sát được**, không chỉ nhìn vào thứ tự record được lưu trong log.

## 2. Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| Partition | Phân vùng dữ liệu/luồng để lưu và xử lý song song | Kafka topic có 12 partition |
| Message key | Giá trị định tuyến hoặc nhóm những message liên quan | orderId, accountId |
| Partitioning function | Quy tắc ánh xạ key sang partition | Hàm hash hoặc routing policy |
| Offset | Vị trí record trong một partition log | Partition 3, offset 542 |
| Producer order | Thứ tự producer gửi/được broker chấp nhận | Event v2 được append sau v1 |
| Delivery order | Thứ tự broker giao record đến consumer | Consumer nhận A rồi B |
| Processing order | Thứ tự handler bắt đầu xử lý | Có thể khởi chạy B trước khi A kết thúc |
| Completion order | Thứ tự kết quả/transaction commit | B có thể commit trước A |
| Per-key order | Thứ tự giữa message chung một khóa | Các event của Order O-101 |
| Per-partition order | Thứ tự record trong một partition | Offset 10 trước offset 11 |
| Global order | Một thứ tự chung cho toàn luồng | Không có sẵn xuyên nhiều Kafka partition |
| Causal order | Thứ tự do quan hệ nguyên nhân–kết quả | Submit trước Cancel của cùng đơn |
| Aggregate version | Phiên bản thay đổi của thực thể nghiệp vụ | Order version 7 |
| Idempotency | Xử lý lại không tạo thêm tác dụng không mong muốn | Event nhận hai lần vẫn chỉ tạo một reservation |
| Sequence gap | Phát hiện thiếu sự kiện theo một contract thứ tự | Đã áp v7 nhưng nhận v9 |
| Rebalance | Phân lại partition cho consumer group | Một partition chuyển từ A sang B |
| Replay/redrive | Đọc lại message cũ từ log, retry hoặc DLQ | v8 xuất hiện khi projection đã ở v10 |

**Lưu ý quan trọng:** Broker có thể bảo đảm thứ tự lưu hoặc giao trong phạm vi nhất định, nhưng không tự bảo đảm thứ tự **commit database**, gửi email, gọi payment provider hoặc ghi side effect khi consumer có nhiều worker.

## 3. Bản đồ thứ tự từ domain tới dữ liệu cuối cùng

~~~text
Domain state transition
          |
          v
Database transaction + Outbox
          |
          v
Producer / Publisher
          |
          v
Broker Topic / Queue
          |
          v
Consumer poll or receive
          |
          v
Application handler / worker pool
          |
          v
Database write / external side effect
          |
          v
ACK or offset commit
~~~

Thứ tự có thể bị phá tại từng ranh giới:

- **Domain → Outbox:** nhiều transaction tạo event cùng aggregate nhưng outbox dispatcher phát sai thứ tự.
- **Publisher → Broker:** nhiều producer cạnh tranh; thứ tự mạng không phản ánh thứ tự commit.
- **Broker → Consumer:** các partition độc lập; không có tổng thứ tự xuyên chúng.
- **Consumer → Worker:** handler dispatch bất đồng bộ, task đến sau chạy nhanh hơn.
- **Worker → DB:** transaction đến sau commit trước hoặc ghi đè state mới.
- **DB → ACK:** DB đã commit nhưng consumer crash trước xác nhận, dẫn tới redelivery.
- **Retry/DLQ → Consumer:** sự kiện cũ quay lại sau sự kiện mới.

Một thiết kế vững thường phải kết hợp **key ổn định + sequence/version + idempotency + transaction/concurrency control + policy retry**. Không có một cờ cấu hình broker duy nhất giải quyết mọi tầng.

## 4. Kafka bảo đảm thứ tự ở đâu?

Apache Kafka lưu record trong mỗi **partition log** theo offset tăng dần. Consumer đọc record từ partition theo thứ tự log trong quá trình poll. Trong một consumer group, một partition thường được gán cho một member tại một thời điểm theo cơ chế assignment.

Ví dụ:

~~~text
Topic: orders.events

Partition 0:
  offset 10: O-101 v1
  offset 11: O-205 v1
  offset 12: O-101 v2
  offset 13: O-205 v2

Partition 1:
  offset 21: O-303 v1
  offset 22: O-303 v2

Partition 2:
  offset  8: O-507 v1
~~~

Kafka biết offset 10 trước offset 12 trong partition 0, nhưng **không có khái niệm offset 12 ở partition 0 xảy ra trước hay sau offset 21 ở partition 1**. Số offset chỉ có ý nghĩa trong partition của nó.

Nếu mọi message của O-101 dùng cùng key, cùng partitioner và cùng số partition trong giai đoạn hoạt động, chúng thường đi cùng partition. Khi producer phát theo domain order, cơ chế đó tạo cơ sở cho per-order log ordering.

### Các điều kiện không được quên

- Cùng key không tự bảo đảm **producer publish theo domain order** khi có nhiều producer cạnh tranh.
- Partition count hoặc thuật toán partitioner thay đổi có thể khiến key đi tới partition khác.
- Poll theo offset không có nghĩa handler side effect hoàn tất theo offset nếu ứng dụng chạy worker song song.
- Crash/rebalance có thể khiến record đã xử lý được giao lại.
- Kafka transaction/exactly-once semantics có phạm vi cụ thể trong hệ Kafka; không tự động áp dụng cho DB độc lập hay external provider.
- Kafka có thể dùng retention/compaction, nên replay toàn bộ lịch sử không phải lúc nào cũng khả thi.

Cách diễn đạt đúng: **Kafka cung cấp thứ tự trong một partition log; tính đúng đắn của state machine còn phụ thuộc producer, key mapping, consumer và storage.**

## 5. Tại sao message key là quyết định nghiệp vụ?

Một key tốt đại diện cho phạm vi cần tuần tự hóa.

| Luồng | Key thường phù hợp | Lý do |
|---|---|---|
| OrderCreated/Submitted/Cancelled | orderId | Các transition của một đơn |
| CustomerProfileChanged | customerId | Phiên bản hồ sơ một khách |
| SubscriptionStarted/Renewed/Cancelled | subscriptionId | Vòng đời gói |
| PaymentAuthorized/Captured/Refunded | paymentId | Trạng thái một payment |
| AccountCredited/Debited | accountId | Invariant số dư theo tài khoản |
| ShipmentDispatched/Delivered | shipmentId | Trật tự chuyến giao |
| StockReserved/Released | stockBucketId hoặc sku:warehouseId | Tranh chấp tồn kho cùng bucket |
| DeviceTelemetry | deviceId | Thứ tự quan sát theo thiết bị |

Không có key chung cho tất cả service. Một event có thể chứa orderId, customerId, sku, paymentId; lựa chọn phụ thuộc **nội dung nào phải được bảo vệ khi nhiều event cạnh tranh**.

### Khóa quá rộng

Key=tenantId đưa tất cả message một tenant vào cùng partition. Nếu tenant có nhiều triệu đơn độc lập, nó tạo hot partition không cần thiết. Key=orderId cho phép các đơn độc lập xử lý song song hơn.

### Khóa quá hẹp

Key=random messageId phân tán mỗi event tới partition khác nhau, làm mất khả năng tập hợp lifecycle của cùng Order. Nếu ứng dụng cần state transition v1→v2→v3, lựa chọn đó nguy hiểm trừ khi có tầng reorder/versioning bền vững.

### Khóa theo ranh giới bất biến

Chọn key **hẹp nhất vẫn bao phủ bất biến cần thứ tự**. Nếu invariant trải trên hai account, partition theo từng account không tự giúp transaction chuyển tiền giữa hai account atomic. Khi đó còn cần ledger/process manager hoặc transactional boundary thích hợp.

## 6. Ví dụ tồn kho: key=orderId khác key=sku

Inventory nhận:

~~~text
Reserve(order=O1, sku=A, qty=2)
Reserve(order=O2, sku=A, qty=5)
Reserve(order=O3, sku=B, qty=3)
~~~

Nếu key=orderId, O1 và O2 có thể chạy trên hai partition, cùng tranh tồn sku=A. Điều đó **không nhất thiết sai** nếu Inventory DB kiểm soát lượng tồn bằng transaction, lock, optimistic concurrency hoặc atomic update.

Nếu key=sku, mọi lệnh với sku=A có thể vào cùng một luồng, giảm xung đột ở cấp application. Tuy nhiên sản phẩm bán chạy sẽ trở thành hot key.

Nếu mỗi kho có lượng tồn riêng, key=sku:warehouseId có thể phân tán theo vị trí, nhưng chuyển hàng giữa hai kho lại là invariant xuyên hai key cần coordination.

**Partition key không thay thế kiểm soát concurrency ở database.** Lựa chọn key giúp bố trí workload và thứ tự; transaction/state machine đảm bảo kết quả khi có race, redelivery hoặc nhiều đường ghi.

## 7. Partition count và số consumer song song

Ví dụ Kafka topic có 8 partition, consumer group có 4 members:

~~~text
Consumer A: partition 0, 4
Consumer B: partition 1, 5
Consumer C: partition 2, 6
Consumer D: partition 3, 7
~~~

Đây là assignment minh họa. Tăng từ 4 lên 8 members có thể phân mỗi partition cho một member. Tăng lên 12 members không tạo thêm parallelism theo partition cho topic 8 partitions; một số members có thể không sở hữu partition của topic ấy.

Nhưng throughput còn phụ thuộc:

- Tốc độ xử lý mỗi message.
- Sự phân bố key, số hot keys.
- Batch size, network, serialization.
- Database connection, locks, external provider quotas.
- Handler concurrency và thứ tự commit.
- Rebalances, retries, message age và backpressure.

Một partition nóng có thể lag nghiêm trọng dù các partition khác rảnh. Tăng số consumer không giải quyết hot partition chỉ có một chuỗi khóa bắt buộc tuần tự.

Không chọn partition count theo số máy hôm nay mà bỏ qua capacity tương lai và chi phí thay đổi mapping khi cần mở rộng.

## 8. Hash(key) và quy tắc serialize key

Một công thức minh họa thường gặp:

~~~text
partition = positiveHash(serializedKey) mod partitionCount
~~~

Đây không phải mô tả bắt buộc của mọi Kafka partitioner hoặc broker. Cấu hình client thực có thể dùng hàm hash, sticky strategy, explicit partition hoặc custom routing khác.

Cùng key về ý nghĩa nghiệp vụ chưa chắc tạo cùng bytes:

~~~text
"ORDER-100"
"order-100"
" ORDER-100 "
UUID text vs UUID binary bytes
tenant + orderId joined without separators
~~~

Một contract key nên mô tả:

~~~text
Stream: ordering.events.v2
Key: tenantId + ":" + canonicalOrderId
Encoding: UTF-8
Case: canonical form, consistent for all producers
Null key: not allowed for lifecycle changes
Owner: Ordering
Partitioner: documented client/routing policy
Partition count migration: explicit change procedure required
Ordering scope: per Order aggregate; no cross-order total order
~~~

Nếu khóa là composite, cần tránh collision. Hai cặp ("AB","C") và ("A","BC") cùng tạo "ABC" nếu nối không delimiter; nếu thành phần có thể chứa delimiter, cần escape hoặc dùng encoding có độ dài rõ.

**Null key** không cho phép dựa vào per-entity routing. Các client có thể phân phối null keys theo chiến lược khác, không bảo đảm chúng về cùng partition.

## 9. Điều gì xảy ra khi tăng số partition?

Giả sử key O-101 được định tuyến tới partition 2 khi topic có 6 partition. Sau khi tăng lên 12, cùng key có thể được định tuyến tới partition 8.

~~~text
Before migration:
  partition 2: O-101 v40, O-101 v41

After migration:
  partition 8: O-101 v42, O-101 v43
~~~

Nếu consumer partition 8 xử lý v42 trước khi partition 2 hoàn tất v41, business completion order có thể đảo. Kafka không nối một total order xuyên hai partition.

Các biện pháp:

1. Xác định từ đầu topic/key nào thật sự cần strict ordering.
2. Chọn partition count dự kiến phù hợp nếu thay đổi nó có rủi ro lớn.
3. Có migration/cutover plan để drain hoặc reconcile dữ liệu cũ theo key.
4. Dùng aggregateVersion và idempotency để phát hiện event cũ, thiếu hoặc sai thứ tự.
5. Có thể dùng topic mới/virtual shards/routing scheme kiểm soát được thay vì tăng partition không kế hoạch.
6. Test tình huống producer cũ và mới cùng tồn tại, consumer lag chưa hết, retry/DLT còn backlog.
7. Không tuyên bố migration an toàn chỉ vì broker hỗ trợ thao tác tăng partition.

Một key có thể giữ cùng phạm vi **trong từng giai đoạn** nhưng không giữ nguyên physical partition xuyên migration. Contract cần phân biệt hai điều đó.

## 10. Key skew và hot partition

Một key nhận 50% toàn bộ message sẽ chiếm nhiều tài nguyên trong partition của nó:

~~~text
p0:   40 messages/second
p1:   45 messages/second
p2:  950 messages/second  <-- one hot aggregate
p3:   52 messages/second
~~~

Thêm partition hoặc consumer instances có thể không giải quyết được nếu một aggregate buộc phải tuần tự.

Hướng xử lý:

- Đo distribution, lag và processing time theo partition/nhóm key.
- Xác định liệu mọi event của key nóng có thực sự cần thứ tự tuyệt đối không.
- Tách aggregate thành những sub-aggregates độc lập nếu domain cho phép.
- Batch/coalesce các cập nhật có semantics tương thích.
- Tối ưu DB contention, serialization, cache và external calls.
- Tách workload theo tenant/capability khi hợp đồng cho phép.
- Đặt backlog/age SLO và backpressure.
- Chấp nhận throughput giới hạn cho một invariant cần strict serializability khi không thể chia nhỏ an toàn.

Không thêm random suffix để chia key nóng nếu điều đó phá invariant. Ví dụ account balance không thể tùy tiện ghi debit vào hai “salted accounts” rồi hợp nhất bằng last-write-wins.

## 11. Producer có thể phá thứ tự trước khi broker nhận

Hai instances của Ordering thay đổi cùng order:

~~~text
Server A commits Order v10
Server B commits Order v11

A is delayed before publishing v10.
B publishes v11.
A publishes v10.
~~~

Cả hai event dùng key=O-101, nhưng broker có thể append v11 trước v10. Key chỉ quyết định partition, không tự biết domain transaction order.

Cần:

- Một nguồn sự thật quyết định aggregateVersion theo transaction.
- Optimistic locking hoặc serialization cho concurrent writes.
- Transactional outbox ghi event intent cùng thay đổi business state.
- Outbox dispatcher có policy giữ order per aggregate, không lấy hai record cùng aggregate chạy tự do.
- Producer ack/failure handling và idempotent send phù hợp.
- Consumer version guard để không ghi đè trạng thái mới bằng event cũ.

Không dùng timestamp của các máy khác nhau làm thứ tự tuyệt đối. Clock skew và network delay khiến thời gian ghi log không thay thế aggregateVersion.

## 12. Transactional Outbox không tự giải quyết ordering

Outbox giảm lỗi dual-write giữa DB và broker:

~~~text
BEGIN
  Update Order to v11
  Insert outbox event for v11
COMMIT

Outbox dispatcher:
  Read pending events
  Publish to broker
  Mark as published
~~~

Điều này giúp event tồn tại bền vững cùng business transaction. Nhưng nếu hai dispatcher publish v11 trước v10, per-aggregate ordering vẫn có vấn đề. Nếu publish thành công nhưng service crash trước mark-published, event có thể được publish lại.

Phải kiểm tra:

- Sequence/order dựa trên aggregateVersion hoặc commit ordering được xác định rõ.
- Dispatcher có thể chạy song song giữa aggregate, nhưng bảo vệ thứ tự trong cùng aggregate.
- Retry publish không cho event sau vượt event trước khi contract cấm.
- EventId không thay đổi khi retry cùng event.
- Consumer xử lý duplicate và stale events.
- Outbox lag, retry count, gap và publish failures được đo.
- Khi migration schema, event cũ còn có thể được gửi sau deploy mới.

Một outbox có bảng ID tự tăng không luôn tương đương commit order theo mọi DB/concurrency scenario; cần thiết kế theo semantics thực tế.

## 13. Versioning ở consumer: chống state đi lùi

Ví dụ projection:

~~~text
orderId = O-101
currentVersion = 7
status = SUBMITTED
~~~

Nếu consumer nhận event version v:

- **v = current+1:** áp event nếu transition hợp lệ, tăng version cùng transaction.
- **v <= current:** duplicate hoặc event cũ; không áp làm state đi lùi.
- **v > current+1:** phát hiện gap; lưu pending bền vững hoặc thực hiện reconciliation theo policy.
- **v không liên quan cùng sequence:** cần contract khác, không ép so sánh sai miền.

Pseudocode:

~~~text
onEvent(event):
    begin transaction
    state = loadForUpdate(event.aggregateId)

    if event.version <= state.appliedVersion:
        commit
        return STALE_OR_DUPLICATE

    if event.version > state.appliedVersion + 1:
        persistPendingGap(event)
        commit
        return WAITING_FOR_PREDECESSOR

    verifyTransition(state, event)
    apply(state, event)
    state.appliedVersion = event.version
    commit
    return APPLIED
~~~

Cần thực hiện so sánh và mutation trong một transaction hoặc compare-and-set atomic, tránh hai worker cùng đọc version cũ rồi ghi đè.

### Không giả định version luôn liên tục nếu contract không nói vậy

Nếu consumer chỉ subscribe một số loại event từ aggregate, version có thể nhảy do những event không liên quan. Nếu bắt đầu từ snapshot v100, cũng không nên đòi event đầu tiên là v1.

Cần chọn **sequence riêng cho stream consumer cần**, hoặc xác định quy tắc áp dụng snapshot/latest state. Điều kiện current+1 chỉ hợp lệ khi consumer có quyền kỳ vọng thấy đầy đủ mọi phiên bản trong cùng dãy.

## 14. Gap detection và trường hợp thiếu predecessor

Ví dụ consumer đang ở v7 nhưng nhận v9:

~~~text
Applied: O-101 v7
Received: O-101 v9
Missing: O-101 v8
~~~

Các nguyên nhân có thể là:

- v8 đến chậm hơn v9 vì publish concurrency.
- v8 nằm tại partition khác sau migration.
- v8 đang ở retry topic hoặc DLQ.
- v8 đã mất do dual-write.
- v8 bị retention/compaction loại bỏ.
- Version sequence không liên tục theo contract của consumer.
- Publisher hoặc consumer có bug.

Các bước xử lý:

1. Ghi nhận gap với eventId, key, expected/actual version và correlation ID.
2. Không áp v9 tùy tiện nếu invariant cần v8.
3. Đưa v9 vào durable pending store có giới hạn tuổi/số lượng, hoặc chặn key theo policy.
4. Tìm v8 từ outbox, event log hay source of truth.
5. Nếu có, replay bền vững với version guard/idempotency.
6. Nếu không, cân nhắc rebuild từ snapshot hoặc reconciliation theo hợp đồng.
7. Alert nếu gap kéo dài quá SLO.

Không lưu gap chỉ trong bộ nhớ rồi ACK broker nếu crash sẽ làm mất event. Cũng không retry nóng vô hạn một event mà cần predecessor chưa có.

## 15. Duplicate và ordering là hai vấn đề khác nhau

Một consumer có thể xử lý v8 thành công:

~~~text
1. Receive O-101 v8
2. Commit database state v8
3. Crash before ACK or commit offset
4. Broker redelivers O-101 v8
~~~

Nếu không có dedup, cùng event có thể gửi email, tạo reservation hoặc điều chỉnh số dư hai lần.

Giải pháp:

- **Inbox/dedup messageId:** ghi consumer+messageId với unique constraint.
- **AggregateVersion:** ngăn áp state cũ hoặc cùng version lần nữa.
- **Business operation key:** hai message khác ID nhưng cùng ý định nghiệp vụ cũng không được tạo tác dụng trùng.
- **Atomic state change:** marker processed và domain mutation nằm trong cùng transaction DB khi có thể.
- **External idempotency:** payment/refund/booking phải có provider idempotency key hoặc lookup và reconciliation.
- **ACK sau durable outcome:** DB commit trước ACK, dự trù redelivery.

Ví dụ:

~~~sql
CREATE TABLE consumed_messages (
  consumer_name VARCHAR(100) NOT NULL,
  message_id VARCHAR(150) NOT NULL,
  consumed_at TIMESTAMP NOT NULL,
  PRIMARY KEY (consumer_name, message_id)
);
~~~

Nếu marker processed được commit riêng **trước** domain mutation, crash có thể làm lần redelivery bị bỏ qua mặc dù business effect chưa xảy ra. Đừng dùng bảng inbox theo cách đó.

## 16. Consumer poll order khác commit order

Kafka consumer poll hai record cùng partition:

~~~text
offset 100: O-101 v8
offset 101: O-101 v9
~~~

Ứng dụng thực hiện:

~~~java
for (ConsumerRecord<String, OrderEvent> record : records) {
    executor.submit(() -> handle(record));
}
~~~

Vì worker pool chạy nhiều thread, v9 có thể commit trước v8. Broker giao record theo offset nhưng ứng dụng không giữ **completion order**.

Các lựa chọn:

- Xử lý tuần tự trong một partition nếu throughput đủ.
- Tạo serial executor/actor theo key.
- Cho phép parallel compute nhưng serialize commit theo key/version.
- Dùng domain operations giao hoán được nếu contract cho phép out-of-order.
- Cài optimistic concurrency/version guard dù đã có serial executor để bảo vệ crash/replay và đường ghi khác.

### Offset commit khi xử lý song song

~~~text
offset 100 = PROCESSING
offset 101 = DONE
offset 102 = DONE
offset 103 = PROCESSING
~~~

Không commit offset qua 102 chỉ vì 101/102 đã hoàn tất. Nếu crash, 100 sẽ bị bỏ lỡ. Cần theo dõi **contiguous completed progress**. Nếu record lỗi được chuyển bền vững sang retry/DLT, commit có thể hợp lệ theo workflow đã thiết kế, nhưng vẫn phải xét thứ tự nghiệp vụ của key.

Không lẫn ACK broker với thành công nghiệp vụ: một message có thể được durable handed off vào pending-gap/reconciliation rồi ACK delivery gốc nếu contract bảo đảm xử lý tiếp đúng.

## 17. Rebalance và task cũ chưa ngừng

Khi consumer mới gia nhập group hoặc một member rời đi, Kafka phân lại partition.

~~~text
Consumer A owns partition 3.
A receives O-101 v8; async task still running.

Rebalance:
  partition 3 moves to Consumer B.
B reads from last committed offset.
A's old task may still be running.
~~~

Trong khi broker có cơ chế group ownership, task ứng dụng của A vẫn có thể ghi DB muộn sau B. Đây là lý do cần:

- Drain/cancel tasks khi partition revoked, với timeout phù hợp.
- Không commit offset trước khi xác nhận phần việc đã hoàn tất.
- Version guard và idempotency ở database.
- Fencing token/epoch khi cần chặn writer cũ; nơi nhận write phải thực sự kiểm tra token.
- Test crash, rolling deploy, long GC pause và network partition.
- Quan sát rebalance count/duration và duplicate processing.

Static membership hoặc cooperative rebalancing có thể giảm disruption trong cấu hình phù hợp, nhưng không thay thế correctness controls.

## 18. Kafka producer retry và tính idempotent

Producer có thể gửi batch A rồi B. Nếu A gặp lỗi tạm thời và được retry sau, cấu hình không phù hợp có thể khiến B được ghi trước A. Producer idempotence và các giới hạn in-flight/retries phù hợp có thể giúp giữ bảo đảm producer-level trong phạm vi partition, theo client/version thực tế.

Không nên suy rằng:

- Idempotent producer bảo đảm đúng causal order từ hai producers độc lập.
- Kafka transaction bảo đảm exactly-once với external payment provider.
- Key giống nhau bảo đảm dữ liệu được publish theo thứ tự commit nghiệp vụ.
- Một send trả về future là event đã được lưu bền ngay.
- Một event ID mới khi retry giúp ích cho dedup của cùng một ý định.

Checklist producer: authoritative owner, stable key/serializer, eventId, aggregateVersion, durable publish/outbox, broker acknowledgement, retry policy và ordered dispatch.

## 19. SQS Standard và SQS FIFO

### SQS Standard

SQS Standard cho khả năng xử lý phân tán linh hoạt nhưng không cung cấp strict ordering guarantee. Có thể nhận duplicate hoặc out-of-order. Consumer cần idempotency và versioning nếu xử lý state.

### SQS FIFO

SQS FIFO dùng **MessageGroupId** để nhóm các message cần trình tự trong cùng group. Nhiều group độc lập có thể xử lý song song. MessageDeduplicationId hoặc content-based deduplication có cơ chế chống gửi trùng trong cửa sổ xác định; không thay thế business idempotency dài hạn.

~~~text
Queue: orders.fifo

Group O-101:
  Created v1
  Submitted v2
  Cancelled v3

Group O-202:
  Created v1
  Submitted v2
~~~

Những điều vẫn phải kiểm tra:

- Producer có gửi cùng group theo đúng thứ tự nghiệp vụ không?
- Nhiều producer cùng group có tạo race không?
- Visibility timeout có đủ dài cho handler không?
- Message chưa được DeleteMessage có làm group bị chặn hoặc redeliver không?
- DLQ/redrive có phá thứ tự mong muốn không?
- MessageGroupId và DeduplicationId có scope ổn định không?
- Side effect đã xảy ra nhưng delete message thất bại được xử lý bằng idempotency chưa?

FIFO hỗ trợ ordering ở phạm vi group, nhưng không bảo đảm một lệnh charge/refund chỉ được thực hiện một lần trên external system.

## 20. RabbitMQ queue và concurrency

RabbitMQ queue có thứ tự enqueue/dequeue trong một số điều kiện; nhưng nhiều consumers, prefetch và reject/requeue có thể khiến thứ tự **hoàn tất** thay đổi.

~~~text
Queue receives: A, B

Consumer 1 receives A -> slow DB transaction
Consumer 2 receives B -> fast DB transaction

Commit order: B before A
~~~

Các biện pháp:

- Định tuyến cùng business key vào cùng queue/shard logic.
- Dùng consumer serial hoặc single-active-consumer khi phù hợp.
- Kiểm soát prefetch, concurrency, ACK/NACK và requeue.
- Có version guard để chống replay và stale write.
- Đánh giá route khi thay đổi số shard queues.
- Kiểm thử poison message và head-of-line blocking.

RabbitMQ không có mô hình Kafka partition-offset giống hệt. Có thể dùng consistent-hash exchange hoặc tự quản routing đến shard queues, nhưng khi đó migration, assignment và bảo đảm key là trách nhiệm kiến trúc của hệ thống.

## 21. So sánh phạm vi bảo đảm

| Hệ thống/cơ chế | Phạm vi thứ tự đáng dựa vào | Không tự bảo đảm |
|---|---|---|
| Kafka partition | Thứ tự log record theo offset | Thứ tự xuyên partitions; DB commit order |
| Kafka consumer group | Assignment partition cho member | Side-effect exactly-once sau crash |
| SQS Standard | Không có strict ordering guarantee | Per-key delivery order |
| SQS FIFO group | Thứ tự theo MessageGroupId khi sử dụng đúng | Global order; external exactly-once |
| RabbitMQ queue | Enqueue/dequeue theo cấu hình và điều kiện | Completion order với competing consumers |
| Transactional outbox | Ghi ý định publish cùng DB transaction | Publish order nếu dispatcher chạy sai |
| Single-thread handler | Thứ tự xử lý trong thread | Duplicate và side effect ngoài transaction |
| Per-key serial executor | Serialization theo key trong runtime | Durability/crash recovery nếu chỉ in memory |
| AggregateVersion check | Ngăn state đi lùi theo contract | Phục hồi event thiếu mà không có nguồn dữ liệu |

Cụm từ “giữ thứ tự” phải luôn kèm **scope và điều kiện**. Hợp đồng event cần viết rõ điều gì được đảm bảo và điều gì không.

## 22. Retry, DLQ và redrive có thể phá thứ tự

~~~text
partition P:
  O-101 v10 -> fails, sent to retry
  O-101 v11 -> succeeds
  O-101 v10 -> returns after delay
~~~

Nếu v10 là event bắt buộc trước v11, việc xử lý v11 ngay có thể tạo state sai. Nếu v11 là full snapshot đủ thông tin, consumer có thể bỏ v10 theo policy. Hai use case khác nhau.

Các chiến lược:

1. **Block partition:** không tiến tới v11 trước khi v10 được xử lý; giữ strict order nhưng có head-of-line blocking cho key khác.
2. **Pause/buffer per key:** cho key độc lập tiếp tục, giữ event v11 của O-101 tại pending store bền vững.
3. **Skip-to-DLQ với version guard:** tiến log nhưng không áp event thiếu predecessor; dùng reconciliation.
4. **Rebuild projection:** khi có nguồn state/snapshot đầy đủ và side effect không bị replay nguy hiểm.
5. **Compensate:** với tác vụ nghiệp vụ không thể đảo bằng overwrite state.

Không dùng mặc định “sau N attempts đưa DLQ rồi xử lý record tiếp” nếu domain bắt buộc tuần tự và hệ thống không có cơ chế kiểm soát gap.

### Poison message và head-of-line blocking

Một record không parse được có thể giữ cả partition dừng. Nếu bỏ qua, có nguy cơ làm thiếu history. Cần quyết định theo loại stream:

- Financial ledger: có thể yêu cầu chặn và điều tra trước.
- Read projection rebuildable: có thể quarantine, đồng bộ snapshot rồi tiếp tục.
- Notification: có thể bỏ thông báo đã hết giá trị, nhưng phải audit nếu có cam kết gửi.
- Inventory reservation: cần xét trạng thái order hiện tại, reservation đã có và tính đúng đắn số lượng.

DLQ là nơi **cách ly lỗi**, không tự giải quyết consistency. Redrive phải kiểm tra current aggregateVersion, idempotency và business deadline.

## 23. Replay, log compaction và dữ liệu lịch sử

Kafka record có thể được đọc lại trong giới hạn retention. Với log compaction, các giá trị cũ cùng key có thể bị loại bớt, phù hợp với một số state changelogs nhưng không đồng nghĩa giữ toàn bộ event history.

Phân biệt:

- **Event sourcing history:** cần lưu đầy đủ các event theo chính sách để tái tạo mọi transition.
- **Compacted state topic:** có thể phục vụ khôi phục latest value, nhưng không bảo đảm còn từng thay đổi trung gian.
- **Read model rebuild:** có thể tái tạo projection từ snapshot/log đủ dữ liệu, không nhất thiết tái thực hiện side effect.
- **Business command replay:** có thể gửi lại thanh toán/email/hoàn tiền; phải có idempotency và authorization.
- **DLQ redrive:** là hành động chủ động xử lý message lỗi cũ, không giống consumer poll bình thường.

Không reset offset về đầu topic mà chưa kiểm tra retention, schema compatibility và tác động side effect. Replaying event cũ khi state đã ở tương lai cần policy stale/gap rõ ràng.

## 24. Cross-partition order và các giao dịch nhiều aggregate

Ví dụ chuyển tiền:

~~~text
Transfer T-900:
  Debit Account A
  Credit Account B
~~~

Nếu key=accountId, Debit A và Credit B có thể vào hai partition khác nhau. **Không có total order xuyên hai partition.** Partition ordering không tạo transaction atomic bao trùm hai tài khoản.

Có thể dùng:

- Ledger/accounting service có transactional boundary phù hợp.
- Process manager/Saga với transferId, state và reconciliation.
- Version riêng từng account, idempotency theo transfer.
- Trạng thái PENDING/CONFIRMED rõ nếu xử lý bất đồng bộ.
- Một coordinator/sequencer trong phạm vi hẹp nếu thực sự cần total order.

Không vì bài toán transfer mà buộc mọi event doanh nghiệp vào một partition duy nhất. Thường chỉ cần per-aggregate order kết hợp workflow consistency, không cần global order.

### Causal order khác timestamp order

Event thời gian máy A là 10:00:00.100 và máy B là 10:00:00.050 không chứng minh B xảy ra trước A theo nghiệp vụ. Network delay, clock skew và async publish khiến wall-clock không đáng tin để làm thứ tự commit tuyệt đối. Nên dùng version/sequence hoặc causal dependency được domain ghi bền.

## 25. Event time, ingestion time và watermark

Trong stream processing, có các mốc:

- **Event time:** khi sự kiện xảy ra theo dữ liệu nguồn.
- **Ingestion time:** khi stream system nhận.
- **Processing time:** khi consumer tính toán.
- **Watermark:** tiến độ event time được dùng trong windowing để chấp nhận độ trễ nhất định.

Ví dụ telemetry e1 xảy ra lúc 10:00:01 nhưng đến sau e2 xảy ra lúc 10:00:02. Broker có thể append e2 trước e1. Stream processor có thể gom theo event-time window để tính analytics, dù processing order khác event-time order.

**Watermark không thay thế aggregateVersion cho OrderSubmitted/Cancelled.** Nó phù hợp hơn với xử lý dữ liệu theo window và late event; state machine cần quy tắc causality và bất biến nghiệp vụ.

Khi có late events, phải quy định cập nhật lại window, side output hoặc bỏ qua sau allowed lateness. Các lựa chọn ảnh hưởng kết quả báo cáo và SLO dữ liệu.

## 26. Message envelope cho per-aggregate ordering

~~~json
{
  "eventId": "evt-8af1",
  "eventType": "OrderSubmitted",
  "eventVersion": 2,
  "aggregateType": "Order",
  "aggregateId": "O-101",
  "aggregateVersion": 8,
  "producer": "ordering-service",
  "occurredAt": "2026-11-11T08:00:00Z",
  "correlationId": "checkout-4e1",
  "causationId": "submit-command-901",
  "payload": {
    "orderId": "O-101",
    "status": "SUBMITTED"
  }
}
~~~

Broker record key có thể là tenantId:aggregateId, đặt riêng với JSON body. Không chỉ tin trường partitionKey nếu producer chưa thực sự gắn nó vào metadata broker.

Các trường hữu ích:

- eventId cho dedup.
- aggregateId và aggregateVersion cho state guard.
- eventType/eventVersion để chọn schema/handler.
- correlationId/causationId để nối flow.
- occurredAt để đo message age, không dùng thay sequence.
- owner/producer để tìm nguồn sự thật.
- tenant scope khi cần, với quyền và bảo vệ dữ liệu.

Một message không nhất thiết cần copy toàn bộ Order object. Giảm payload giúp bảo vệ dữ liệu, tránh coupling và giảm chi phí broker.

## 27. Java: Kafka producer có key ổn định

Ví dụ Spring Kafka:

~~~java
import org.springframework.kafka.core.KafkaTemplate;

public final class OrderEventPublisher {
    private final KafkaTemplate<String, OrderEvent> template;

    public OrderEventPublisher(KafkaTemplate<String, OrderEvent> template) {
        this.template = template;
    }

    public void publish(OrderEvent event) {
        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        String key = event.tenantId() + ":" + event.orderId();
        template.send("ordering.events", key, event);

        // Production cần quan sát kết quả send bất đồng bộ;
        // dùng outbox hoặc cơ chế publish tin cậy phù hợp,
        // không coi send() trả về là broker đã lưu thành công.
    }
}
~~~

Đây là ví dụ khái niệm, giả định OrderEvent có accessor và serializer được cấu hình. Trong production cần định nghĩa canonical key, schema evolution, acknowledgement, retry/idempotent producer và phát sự kiện theo domain sequence. Nếu nhiều Order instances publish cùng key, consumer vẫn cần version guard.

## 28. Java: consumer sử dụng version guard

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {
    private final OrderProjectionUseCase useCase;

    public OrderProjectionListener(OrderProjectionUseCase useCase) {
        this.useCase = useCase;
    }

    @KafkaListener(
        topics = "ordering.events",
        groupId = "order-projection"
    )
    public void consume(OrderEvent event) {
        useCase.applyIdempotentlyWithVersionGuard(event);
    }
}
~~~

Service layer pseudocode:

~~~text
@Transactional
applyIdempotentlyWithVersionGuard(event):
  state = repository.lockByOrderId(event.orderId)

  if inbox contains event.eventId:
      return ALREADY_APPLIED

  if event.aggregateVersion < state.expectedNext:
      return STALE_EVENT

  if event.aggregateVersion > state.expectedNext:
      persistGapForReconciliation(event)
      return WAITING_FOR_GAP

  domainCheckAndApply(event, state)
  state.expectedNext++
  inbox.insert(event.eventId)
  commit
  return APPLIED
~~~

Pseudocode chưa phải code compilable: cần kiểu dữ liệu, transaction/repository, error mapping và idempotency store. Đặc biệt nếu lưu pending gap rồi tiến Kafka offset, pending store phải bền vững và có consumer/job phục hồi. Cách xử lý skip/commit khi retry phụ thuộc policy ordering của ứng dụng.

Spring Kafka có nhiều chế độ listener concurrency, acknowledgement, retry handler và DLT; phải xác nhận behavior theo version/config thật. Không mặc định annotation bảo đảm transactional exactly-once với DB ngoài Kafka.

## 29. Song song giữa key, tuần tự trong key

Mục tiêu phổ biến:

~~~text
Incoming stream
      |
      v
Per-key serial dispatcher
      |
      +--> O-101: v1 -> v2 -> v3
      |
      +--> O-202: v1 -> v2
      |
      +--> O-303: v1 -> v2 -> v3 -> v4
~~~

Cho các key độc lập xử lý song song, nhưng với một key có strict order, chỉ cho transition tiếp theo commit khi predecessor đã hoàn tất hoặc policy đã xử lý hợp lệ.

Cần trả lời:

- Queue per-key có ở memory hay durable storage?
- Làm sao giới hạn hàng triệu key hoặc key rất nóng?
- Khi key A lỗi, chỉ chặn A hay cả partition?
- Offset commit tiến đúng contiguous progress ra sao?
- Rebalance có task đang chạy không, và ai là owner mới?
- Nếu có external side effect, idempotency key được tạo theo nghiệp vụ thế nào?
- Có cần strict processing order hay chỉ cần monotonic final state?

Một in-memory serial executor có thể giúp concurrency trong runtime nhưng **không tự giải quyết crash/recovery**. Nếu ACK trước khi durable handoff, công việc có thể mất.

## 30. Quy trình điều tra sai thứ tự trong production

Khi phát hiện projection Order từ CANCELLED quay lại SUBMITTED:

1. Xác định orderId, expected/applied version, eventId, topic, partition, offset.
2. Kiểm tra producer key bytes, partitioner, số partition và thời điểm migration.
3. So sánh domain transaction order và outbox publish order.
4. Kiểm tra producer retry, multiple producers và acknowledgement.
5. Kiểm tra consumer concurrency, async worker và thời điểm DB commit.
6. Kiểm tra offset commit, rebalance và task cũ còn in-flight.
7. Kiểm tra retry/DLT và redrive cũ.
8. Đánh giá inbox/idempotency và transaction boundary.
9. Chọn khôi phục: pause key/partition, fix handler, rebuild projection hoặc reconciliation.
10. Trước khi replay, kiểm tra side effects bên ngoài và business validity.
11. Theo dõi gap count, stale event rate, duplicate rate và SLO sau sửa.

Không chạy reset-offset toàn topic để chữa state corruption nếu chưa biết business side effects có an toàn khi replay không.

## 31. Observability cho phân vùng và ordering

| Metric | Tín hiệu |
|---|---|
| Produced records/bytes per partition | Cân bằng tải |
| Consumer lag per partition | Partition nào bị nghẽn |
| Oldest unprocessed message age | Độ trễ tác động business |
| Handler duration by operation | Điểm nghẽn xử lý |
| In-flight work per partition | Concurrency có kiểm soát |
| Sequence gap count/age | Thiếu predecessor |
| Stale/duplicate event count | Replay và xử lý lại |
| Retry/DLT entries by code | Poison hoặc dependency lỗi |
| Rebalance count/duration | Đổi ownership gây gián đoạn |
| Outbox dispatch lag | Publish chậm hoặc kẹt |
| Business completion latency | Đo đúng kết quả người dùng |
| Hot-key skew/top-K | Key làm tắc partition |
| Reconciliation backlog | Lỗi chưa có kết quả cuối |

Không dùng raw orderId, accountId hoặc customerId làm metric labels có cardinality cao. Dùng aggregated metrics và log/trace được bảo vệ để điều tra một ID cụ thể.

Alert có giá trị khi chỉ ra hành động: một partition lag cao, sequence gap vượt thời hạn, một key lỗi giữ toàn partition, retries tăng sau rollout hoặc redrive khiến stale-event rate bất thường.

## 32. Test scenarios bắt buộc cho ordering

### Test 1: nhiều aggregate

Gửi xen kẽ O-101 v1→v2 và O-202 v1→v2. Hai order có thể xử lý song song nhưng state cuối của từng order phải đúng.

### Test 2: hai producers

A commit v10 nhưng publish chậm; B publish v11 trước. Consumer phải phát hiện gap hoặc producer phải bảo đảm ordered dispatch.

### Test 3: duplicate sau crash

Consumer commit DB rồi chết trước ACK. Record được redeliver; hệ thống không được tạo thêm side effect.

### Test 4: parallel handler

Cố làm handler v8 chậm hơn v9. Xác minh per-key serialization hoặc version guard chặn stale overwrite.

### Test 5: rebalance lúc task đang chạy

A vẫn có task chưa xong, B nhận partition. Không cho task cũ ghi state lùi hoặc nhân đôi payment.

### Test 6: retry/DLQ giữa chuỗi

v10 lỗi và vào DLT, v11 được giao sau. Kiểm tra chính sách block/pending/reconciliation chính xác.

### Test 7: tăng partition count

Mô phỏng topic chuyển từ 6 lên 12 partition khi còn backlog/retry. Cùng key có thể đi nơi khác; cutover phải không làm mất correctness.

### Test 8: hot key

Một key chiếm 40% traffic. Đo lag, capacity và thử backpressure; không tăng partition vô nghĩa khi key không thể chia.

### Test 9: replay event cũ

Sau khi state đã v20, redrive v18. Không cho projection đi lùi hoặc tạo lại side effect.

### Test 10: nguồn sự thật và schema

Consumer chỉ subscribe subset events, version có gap hợp lệ; đảm bảo logic không chặn vĩnh viễn vì giả định sequence không đúng contract.

Kết quả test phải xác nhận **business state và số lần side effect**, không chỉ so sánh thứ tự offset trên broker.

## 33. Ví dụ e-commerce: ba luồng khác nhau

**Order lifecycle:** Key theo orderId để các transition Created/Submitted/Cancelled đi cùng phạm vi. AggregateVersion và inbox ngăn stale/duplicate. Các Order khác nhau có thể xử lý song song.

**Inventory reservations:** Chọn key theo stock bucket/SKU-location nếu cần serialize tranh tồn trong một bucket, nhưng vẫn dùng transaction kiểm soát số lượng. Nếu hai SKU được reserve cho một đơn, workflow có thể cần compensation khi một SKU thất bại.

**Payment events:** Key theo paymentId/transactionId của state machine. Authorization, Capture và Refund có side effect với provider; thứ tự broker không thay thế idempotency key và reconciliation. Với account balance, invariant có thể cần ledger-level design khác.

Một hệ thống có thể dùng key khác nhau cho ba stream vì domain ownership và bất biến khác nhau. Đó là chủ ý tốt, không phải thiếu nhất quán.

## 34. Bài tập tự tính và giải thích

**Câu 1:** Kafka topic 6 partitions, một group có 10 consumers. Có tối đa bao nhiêu members được gán partition của topic trong mô hình thông thường?  
**Gợi ý:** Tối đa 6 member cùng có partition của topic đó, số còn lại có thể idle với topic ấy; throughput vẫn phụ thuộc tải và processing.

**Câu 2:** Hai messages O-101 v8/v9 cùng partition, nhưng handler chạy bằng hai futures. Kafka có bảo đảm v8 commit DB trước v9 không?  
**Gợi ý:** Không. Log order khác completion order. Cần serialization hoặc atomic version guard.

**Câu 3:** Một producer dùng key=tenantId và tenant lớn gây 70% traffic. Có nên chuyển sang key=orderId?  
**Gợi ý:** Chỉ khi event của các đơn khác nhau độc lập theo invariant. Nếu phải serialize toàn tenant vì rule khác, đổi key có thể phá correctness.

**Câu 4:** Sau khi tăng partition count, cùng orderId nằm ở partition mới. Per-order business completion order có tự giữ không?  
**Gợi ý:** Không thể mặc định. Need migration/cutover strategy, backlog drain hoặc version/reconciliation.

**Câu 5:** Consumer nhận v12 nhưng thiếu v11. Nên ACK rồi bỏ?  
**Gợi ý:** Phụ thuộc contract. Với strict sequence, lưu bền pending gap hoặc chặn; không làm mất message. Với full snapshot superseding, có thể có policy khác.

**Câu 6:** Payment event được giao lại sau khi provider capture thành công. Chỉ kiểm tra Kafka offset có đủ chống capture trùng không?  
**Gợi ý:** Không. Cần business idempotency, operation key và provider reconciliation.

**Câu 7:** SQS FIFO group O-101 bảo đảm thứ tự, vậy hai producers cùng gửi group đó có tự biết event nào là nguyên nhân của event nào?  
**Gợi ý:** Không. Producer phải bảo đảm domain sequence, state cần version.

**Câu 8:** Kafka DLT chứa v3 của một aggregate, trong lúc main consumer đã áp v4. Có thể replay v3 nguyên trạng không?  
**Gợi ý:** Phải kiểm tra snapshot/delta semantics, state hiện tại và side effects; replay mù có thể phá dữ liệu.

## 35. Checklist trước khi đưa production

### Domain và partition key

- [ ] Đã xác định chính xác invariant yêu cầu thứ tự.
- [ ] Ghi rõ guarantee là per-key, per-partition, per-group hay cross-key.
- [ ] Key không quá rộng hoặc quá hẹp so với business scope.
- [ ] Key serialization, normalization và null policy ổn định.
- [ ] Có kế hoạch cho hot key và tăng partition count.
- [ ] Có eventId và aggregateVersion/sequence phù hợp.
- [ ] Biết event là full snapshot hay delta.
- [ ] Không dùng timestamp xuyên máy như total order tuyệt đối.

### Producer và broker

- [ ] Producer/domain owner được xác định rõ.
- [ ] DB transaction + publish có cơ chế tin cậy như outbox nếu cần.
- [ ] Concurrent publisher không tạo sai order per aggregate.
- [ ] Producer retry/idempotence/in-flight có cấu hình phù hợp.
- [ ] Hiểu scope ordering thật của Kafka/SQS/RabbitMQ.
- [ ] Partition change/key migration có cutover và recovery plan.
- [ ] Retention/compaction phù hợp yêu cầu replay.

### Consumer và xử lý lỗi

- [ ] Consumer không nhầm poll order với completion order.
- [ ] Có atomic version guard/optimistic locking.
- [ ] Idempotency xử lý duplicate sau DB commit trước ACK.
- [ ] Với parallel work, offset commit theo completed contiguous progress.
- [ ] Rebalance không để old worker ghi state lùi.
- [ ] Gaps được lưu bền và có reconciliation workflow.
- [ ] Retry/DLT nêu rõ sẽ chặn key/partition hay cho tiếp tục.
- [ ] Redrive kiểm tra state và external side effects hiện tại.
- [ ] Không ACK trước durable business outcome hoặc durable handoff.
- [ ] External API có idempotency/lookup khi kết quả chưa rõ.

### Vận hành và kiểm chứng

- [ ] Theo dõi per-partition lag, hot key skew, oldest message age.
- [ ] Có metric sequence gap, stale/duplicate, retries, rebalance.
- [ ] Có runbook cho poison message và out-of-order state.
- [ ] Đã test producer concurrency, crash, rebalance, migration.
- [ ] Đã test replay event cũ và DLT redrive.
- [ ] SLO đo business completion, không chỉ consumer uptime.
- [ ] Không tạo metric cardinality/PII quá mức.
- [ ] Tài liệu ghi rõ cả guarantee và trường hợp **không** được bảo đảm.

## 36. Kết luận

**Partition là đơn vị chia tải; message key là quyết định gắn với ranh giới nghiệp vụ; thứ tự được bảo đảm chỉ trong một phạm vi đã xác định.** Kafka có thứ tự log trong từng partition, SQS FIFO gắn thứ tự với MessageGroupId, còn RabbitMQ phụ thuộc queue routing, consumer concurrency và ACK/requeue. Không hệ thống nào tự biến delivery order thành chính xác một lần thực thi side effect trong database hoặc provider bên ngoài.

Thiết kế đáng tin cậy kết hợp **stable per-aggregate key, ordered producer/outbox, aggregate version, atomic consumer state, idempotency, retry/DLT có hiểu về ordering và migration/replay có kiểm soát**. Cho các aggregate độc lập xử lý song song khi không cần thứ tự chung; giữ strict ordering ở nơi bất biến đòi hỏi và dùng observability/test để chứng minh những lời hứa đó thực sự được giữ.
