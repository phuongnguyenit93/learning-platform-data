# Phân biệt broker, producer, consumer và nhóm consumer

Trong kiến trúc microservices, **giao tiếp bất đồng bộ** cho phép một dịch vụ gửi thông điệp và tiếp tục công việc mà không phải chờ dịch vụ đích hoàn thành ngay. Để thiết kế đúng cần phân biệt bốn thành phần:

- **Producer** là bên tạo và gửi thông điệp.
- **Broker** là hệ thống nhận, lưu và định tuyến hoặc phục vụ thông điệp theo giao thức và cấu hình.
- **Consumer** là bên nhận, đọc và xử lý thông điệp trong phạm vi nghiệp vụ mình sở hữu.
- **Consumer group** là một tập consumer phối hợp chia khối lượng đọc/xử lý theo cơ chế của hệ thống nhắn tin. Với Apache Kafka, nhóm có group ID và tiến độ offset riêng; với RabbitMQ queue cổ điển, nhiều worker cùng queue là mô hình competing consumers tương tự về mục đích chia việc nhưng không phải cùng một cơ chế.

Bốn vai trò trả lời bốn câu hỏi khác nhau: **Ai công bố? Ai vận chuyển và giữ? Ai thực thi? Những instance nào chia nhau công việc?** Không nên gọi mọi subscriber là “consumer group”, hoặc mặc định broker đảm bảo mọi business action chỉ xảy ra đúng một lần.

Bài này áp dụng cho một hệ thống thương mại điện tử gồm Ordering, Inventory, Payments, Notifications và Analytics. Cách diễn giải phân biệt nguyên lý chung với hành vi đặc thù của Kafka và RabbitMQ, tránh áp dụng nhầm partition, offset hay ACK giữa các nền tảng.

## 1. Sơ đồ tổng quát

~~~text
         PRODUCER                            BROKER
+----------------------+     +------------------------------------+
| Ordering Service     |     | Topic / Exchange / Queue           |
| - commit Order       |---->| - nhận và route message             |
| - outbox publisher   |     | - lưu và phân phối theo cấu hình    |
+----------------------+     +------------------------------------+
                                             |
                          +------------------+-------------------+
                          |                  |                   |
                          v                  v                   v
                  Analytics group      Notify group        Audit group
                   +-----------+       +-----------+       +-----------+
                   | Worker A1 |       | Worker N1 |       | Worker U1 |
                   | Worker A2 |       | Worker N2 |       +-----------+
                   +-----------+       +-----------+
                      chia tải             chia tải
~~~

Một event OrderPlaced có thể được mỗi nhóm logic tiếp nhận riêng: Analytics cập nhật báo cáo, Notifications tạo yêu cầu gửi email và Audit lưu lịch sử. Bên trong nhóm Analytics, các worker có thể chia nhau partition hoặc message; **không cần tất cả worker cùng xử lý mỗi event**.

Nếu cần nhiều ứng dụng cùng nhận mọi event, phải tạo subscription/group/queue độc lập phù hợp với broker. Nếu chỉ muốn tăng năng lực xử lý của một ứng dụng, tăng consumer instance trong cùng đơn vị chia tải theo giới hạn nền tảng.

## 2. Bảng phân biệt bốn vai trò

| Vai trò | Chức năng chủ yếu | Đối tượng nó biết | Trách nhiệm không thuộc về nó |
| --- | --- | --- | --- |
| Producer | Tạo message, chọn key/destination, publish, quản lý kết quả gửi | Hợp đồng message và nơi công bố | Chứng minh mọi subscriber đã xử lý xong |
| Broker | Nhận, định tuyến, giữ, phân phối hoặc phục vụ log; quản lý transport | Topic, queue, partition, subscriber/connection | Xác định bất biến thanh toán, kho hoặc đơn hàng |
| Consumer | Deserialize, xử lý nghiệp vụ, ghi dữ liệu, xác nhận tiến độ | Contract, business key, local transaction | Cập nhật trực tiếp dữ liệu của service khác |
| Consumer group | Phối hợp các consumer để chia việc trên nguồn dữ liệu | Thành viên, assignment/đơn vị tiến độ theo nền tảng | Làm cho mọi ứng dụng khác nhau đều nhận message |

Một service có thể vừa là consumer vừa là producer. Ví dụ Inventory **consume** ReserveStock command, kiểm tra số lượng tồn rồi **produce** StockReserved event sau khi transaction giữ hàng thành công.

## 3. Producer: ai tạo và phát thông điệp?

Producer có thể là API handler, application service, worker hoặc một publisher đọc transactional outbox. Nhiệm vụ cốt lõi là công bố **đúng thông điệp, đúng thời điểm, đúng nguồn có thẩm quyền**.

Ví dụ Ordering sở hữu Order nên có quyền phát OrderPlaced. Analytics đọc OrderPlaced để tính báo cáo, nhưng không trở thành owner của sự kiện OrderPlaced.

Producer cần xác định:

1. **Ngữ nghĩa:** command yêu cầu việc gì hay event xác nhận fact nào đã xảy ra?
2. **Destination:** topic, queue, exchange/routing key nào?
3. **Key:** orderId, customerId hay business ID nào cần bảo đảm phân vùng/thứ tự?
4. **Schema:** tên message, schemaVersion, dữ liệu cần thiết, đơn vị tiền, thời gian và semantics.
5. **Identity:** messageId/eventId/commandId ổn định để truy vết và xử lý trùng.
6. **Reliability:** lúc nào được coi là publish đã được broker chấp nhận?
7. **Retry:** nếu mất ACK hoặc timeout, gửi lại như thế nào?
8. **Security:** producer có quyền publish đích đó không, payload có thông tin nhạy cảm không?
9. **Observability:** publish failure, retry, outbox age và throughput có được đo không?

Ví dụ integration event:

~~~json
{
  "eventId": "evt-order-1001-v1",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "producer": "ordering",
  "occurredAt": "2026-11-11T09:21:15Z",
  "aggregateId": "ord-1001",
  "aggregateVersion": 1,
  "correlationId": "checkout-888",
  "payload": {
    "orderId": "ord-1001",
    "customerId": "cust-71",
    "total": {"amountMinor": 159900, "currency": "VND"}
  }
}
~~~

Event này mô tả một đơn đã được ghi nhận, **không** có nghĩa email xác nhận đã gửi, tồn kho đã giữ hay thanh toán đã hoàn tất. Broker ACK cho producer cũng không chứng minh các bước phía consumer đã thành công.

### 3.1. Đừng publish event không tương ứng trạng thái đã commit

Một lỗi thường gặp:

~~~text
1. INSERT INTO orders ...
2. COMMIT
3. Publish OrderPlaced
4. Process crash giữa bước 2 và bước 3
=> Có đơn hàng nhưng sự kiện không được công bố.
~~~

Dùng **transactional outbox** để lưu Order và bản ghi event trong cùng giao dịch database:

~~~text
BEGIN TRANSACTION
  INSERT INTO orders ...
  INSERT INTO outbox (event_id, type, payload, created_at)
COMMIT

Outbox publisher:
  đọc record chưa phát
  gửi tới broker
  ghi nhận đã phát hoặc retry
~~~

Nếu publisher đã gửi nhưng chết trước khi đánh dấu, nó có thể gửi trùng khi chạy lại. Producer cần giữ nguyên eventId của cùng logical event và consumer phải idempotent. Outbox giải quyết bài toán dual-write giữa state và bản ghi gửi, không tạo giao dịch nguyên tử với database của các consumer.

## 4. Broker: hạ tầng truyền thông trung gian

Broker có thể hỗ trợ:

- Nhận message từ producer và xác nhận theo cấu hình durability.
- Route theo topic, queue, exchange, routing key hoặc partition.
- Lưu message đến khi được xử lý hoặc hết retention, tùy kiểu broker.
- Phục vụ consumer pull/poll hoặc đẩy delivery đến consumer.
- Giám sát client connection, phân phối tải, retry/redelivery, offset/ACK tùy nền tảng.
- Chặn truy cập trái phép, áp quota, replication và cơ chế hồi phục sau node failure.
- Cung cấp metric về backlog, throughput, latency, disk/memory và availability.

**Broker không tự chạy nghiệp vụ của Ordering hay Inventory.** Một message được broker giữ an toàn không chứng minh business invariant của consumer đã được kiểm tra hoặc side effect đã hoàn tất.

### 4.1. Các khái niệm hạ tầng không đồng nghĩa nhau

| Khái niệm | Ý nghĩa cần nhớ |
| --- | --- |
| Topic | Kênh/luồng message; trong Kafka gồm các partition |
| Partition | Một log có thứ tự riêng trong Kafka, hỗ trợ phân tải theo key |
| Offset | Vị trí record trong partition; consumer group theo dõi tiến độ |
| Queue | Hàng chờ để giao message cho worker, thường có ACK/NACK |
| Exchange | Điểm nhận message trong RabbitMQ và định tuyến đến queue |
| Routing key | Thuộc tính để định tuyến trong RabbitMQ |
| Consumer group | Nhóm consumer phối hợp đọc, có semantics cụ thể trong Kafka |
| Subscription | Quan hệ đăng ký nhận một luồng/loại message |
| Acknowledgment | Tín hiệu chấp nhận/giao/xử lý tùy giao thức và mức |
| Retention | Thời gian/kích thước broker giữ record cho phép đọc lại |
| DLQ/DLT | Đích chứa message không xử lý thành công sau chính sách retry |

Không nên suy ra “message đã ACK thì biến mất” đối với Kafka: commit offset chỉ ghi tiến độ nhóm, còn record vẫn tồn tại theo chính sách retention hoặc compaction. Trong queue cổ điển, khi delivery được ACK hợp lệ, message thường được xóa khỏi queue theo semantics của loại queue đó.

## 5. Kafka: topic, partition và offset

Kafka lưu event trong topic nhiều partition:

~~~text
Topic: order-events

Partition 0: offset 0, 1, 2, 3, ...
Partition 1: offset 0, 1, 2, 3, ...
Partition 2: offset 0, 1, 2, 3, ...
~~~

Producer gửi record vào một partition. Nếu record của cùng orderId dùng key ổn định, chúng thường được định tuyến vào cùng partition theo partitioner, giúp xử lý theo thứ tự của partition. **Kafka không bảo đảm thứ tự toàn topic khi có nhiều partition.**

Consumer thường dùng poll/fetch để đọc record, xử lý rồi commit offset theo chiến lược cấu hình. Một topic có thể được nhiều consumer group độc lập đọc; mỗi group có tiến độ riêng. Khi một group đã xử lý record, group khác vẫn có thể đọc cùng record.

Ví dụ:

~~~text
Topic order-events: P0 P1 P2 P3

Group: analytics-orders
  analytics-1 -> P0,P1
  analytics-2 -> P2,P3

Group: notification-orders
  notify-1 -> P0,P1,P2,P3

Group: audit-orders
  audit-1 -> P0,P1,P2,P3
~~~

Analytics có hai instance chia việc trong group, còn Notifications và Audit mỗi bên đều có quyền đọc toàn bộ luồng theo tiến độ riêng.

### 5.1. Partition ảnh hưởng khả năng scale

Trong cơ chế group assignment tiêu chuẩn, một partition của topic được giao cho tối đa một active consumer trong group tại một thời điểm. Nếu group có bốn partition nhưng chạy sáu consumer, ít nhất hai instance có thể không có partition để đọc. Tăng replicas sẽ không tăng song song vô hạn.

Nếu một customerId rất nóng dẫn đến phần lớn event vào cùng partition, một consumer có thể thành nút cổ chai dù các consumer khác đang rảnh. Cần xem lại key, partitioning hoặc mô hình workload, nhưng đổi key khi cần ordering có thể làm mất thứ tự logic.

### 5.2. Consumer group trong Kafka

Group ID đại diện một đơn vị tiêu thụ logic:

~~~properties
analytics.group.id=analytics-order-projection
notifications.group.id=order-notifications
audit.group.id=order-audit
~~~

Nếu Analytics và Notifications dùng **cùng group.id**, Kafka có thể phân partition giữa hai ứng dụng: mỗi bên chỉ thấy một phần event. Đây là lỗi thiết kế nghiêm trọng khi cả hai cần nhận đầy đủ OrderPlaced.

Ngược lại, nếu mỗi replica Notifications được cấp group ID khác nhau, chúng có thể đều đọc mỗi record và tạo nhiều yêu cầu gửi email. Các replica để chia tải của **cùng chức năng** phải phối hợp trong một group, với xử lý idempotency riêng.

## 6. RabbitMQ: exchange, binding và queue

Trong RabbitMQ với AMQP 0-9-1, producer có thể publish vào exchange. Exchange áp dụng routing/binding để gửi bản sao đến một hoặc nhiều queue:

~~~text
Ordering
  |
  v
Exchange: orders.events
  | binding: order.placed
  +--> queue: analytics.order-placed
  |       -> analytics worker A1
  |       -> analytics worker A2
  |
  +--> queue: notify.order-placed
  |       -> notification worker N1
  |       -> notification worker N2
  |
  +--> queue: audit.order-placed
          -> audit worker U1
~~~

Mỗi **queue riêng** có thể nhận bản sao message theo binding. Nhiều consumer trên **một queue** cạnh tranh nhận delivery; thường một consumer nhận một lần giao, broker có thể redeliver nếu ACK thiếu hoặc connection mất.

RabbitMQ queue cổ điển không có group.id và offset log giống Kafka. Có thể gọi các worker dùng chung queue là “nhóm consumer” trong ngôn ngữ giải thích, nhưng đừng áp dụng các quy tắc Kafka partition/replay sang queue. RabbitMQ Streams có semantics khác và cần đọc theo loại destination được triển khai.

### 6.1. Quy tắc fan-out và chia việc

- **Muốn Analytics và Notifications đều biết event:** hai queue hoặc subscription độc lập.
- **Muốn Analytics xử lý nhanh hơn:** nhiều worker cùng queue analytics.
- **Muốn Audit đọc lịch sử:** cần thiết kế khả năng giữ/replay dữ liệu phù hợp, vì queue ACK không tự cung cấp log lịch sử như Kafka.
- **Muốn gửi một command tới một owner:** dùng queue/destination mà owner kiểm soát, tránh nhiều business handler khác nhau cùng thực thi một tác vụ.

## 7. Consumer: bên xử lý và quyết định side effect

Consumer là instance thực tế nhận message từ broker: một pod, process, worker thread hoặc client được quản lý bởi framework. Một consumer tốt phải xử lý:

1. Deserialize và kiểm tra schema/version.
2. Xác nhận messageType phù hợp với handler.
3. Kiểm tra quyền/nguồn thông điệp nếu ranh giới tin cậy yêu cầu.
4. Xác định message ID và business operation ID để chống trùng.
5. Kiểm tra invariant cục bộ và điều kiện đồng thời.
6. Thực hiện thay đổi trong local transaction.
7. Ghi inbox/processed ID cùng transaction nếu dùng idempotency database.
8. Ghi event kết quả vào outbox nếu cần.
9. Chỉ ACK hoặc commit offset sau khi đạt mốc lưu trạng thái theo hợp đồng.
10. Ghi metrics, trace, retry, DLQ và trạng thái lỗi để phục hồi.

Ví dụ Inventory nhận ReserveStock: nó **không** tin rằng chỉ vì message đến từ Ordering thì kho chắc chắn còn hàng. Nó phải kiểm tra trạng thái Inventory authoritative, bảo vệ race condition khi hai command cùng giữ một SKU, rồi công bố StockReserved hoặc ReservationRejected.

Ví dụ Analytics nhận OrderPlaced: nó cập nhật projection/reporting của chính nó, không tự sửa bảng Order do Ordering sở hữu.

### 7.1. Một consumer có thể vừa nhận event vừa gửi command

Notifications nhận event OrderPlaced rồi quyết định tạo command nội bộ SendReceiptEmail. Khi email provider xác nhận nhận tác vụ theo contract, Notifications có thể phát EmailDispatched. Đây là chuỗi hành vi của consumer/producer trong cùng service, không thay đổi ý nghĩa nguyên bản của OrderPlaced.

## 8. Consumer group: chia việc trong một ứng dụng logic

Hãy phân biệt hai mong muốn:

**Fan-out:** “Mỗi ứng dụng Analytics, Notifications và Audit đều phải nhận bản tin.” Giải pháp là những subscription/group/queue độc lập.

**Load sharing:** “Analytics có nhiều bản tin, hãy chia cho các worker của Analytics.” Giải pháp là nhiều consumer trong cùng group/queue.

~~~text
                       OrderPlaced
                           |
                           v
                     Topic / Exchange
                        /    |    \
                       /     |     \
                Analytics  Notify   Audit
                group      group    group
               A1 A2 A3    N1 N2     U1
                 chia tải   chia tải  nhận độc lập
~~~

Mỗi consumer group có thể scale theo nhu cầu của ứng dụng. Một consumer group không bao trùm tất cả service có subscribe topic.

### 8.1. Rebalance trong Kafka

Khi consumer vào hoặc rời group, assignment có thể thay đổi. Kafka thực hiện rebalance theo coordinator và giao thức/group protocol được dùng. Consumer mới có thể nhận lại partition từ consumer cũ, gồm message mà phiên bản cũ đã xử lý business side effect nhưng chưa commit offset.

Vì vậy consumer phải:

- Có idempotency tại database hoặc external effect.
- Không commit offset sớm nếu bản tin còn đang xử lý.
- Cấu hình thời gian xử lý, heartbeat và graceful shutdown phù hợp.
- Theo dõi rebalance count/duration, lag và số lần redelivery.
- Xử lý mixed-version an toàn trong rolling deployment.

Số instance tăng giảm có thể giúp scale, nhưng cũng khiến rebalance và temporary pause; autoscaling phải cân bằng lợi ích throughput với chi phí đó.

### 8.2. Competing consumers trong RabbitMQ

Các worker cùng subscribe một queue được phân phối các message theo availability, prefetch, priority và policy của queue. Khi một worker chết với message chưa ACK, broker có thể redeliver. Một message có thể không được xử lý đúng một lần ở tầng business.

Trong trường hợp cần mọi ứng dụng đều nhận một bản sao, tạo thêm queue/binding, không chỉ thêm worker ứng dụng khác vào queue hiện có.

## 9. Delivery guarantees và các mốc xác nhận

| Mốc | Điều đã biết | Điều vẫn chưa biết |
| --- | --- | --- |
| Producer gọi send | Đã yêu cầu client library gửi | Broker đã lưu hay chưa |
| Broker ACK/confirm | Broker chấp nhận theo cấu hình | Consumer đã hoàn tất hay chưa |
| Consumer nhận message | Client đã đọc delivery/record | Local transaction đã commit hay chưa |
| Consumer commit database | Side effect cục bộ được lưu | Broker đã ghi nhận tiến độ hay chưa |
| Consumer ACK/commit offset | Broker biết tiến độ theo mô hình | External side effect có bị lặp hay không |
| Event kết quả được phát | Owner công bố một business fact | Mọi subscriber đã đồng bộ ngay hay chưa |

Ba mô hình thường được nhắc:

- **At-most-once:** chọn không giao lại sau một mốc, có thể mất message nếu fail giữa chừng.
- **At-least-once:** broker/client giao lại nếu tiến độ chưa xác nhận, có thể gây duplicate, cần idempotency.
- **Exactly-once trong một phạm vi:** một số hệ thống cung cấp transaction/deduplication trong ranh giới xác định; không tự suy ra “payment gateway và database khác cũng chỉ chịu tác động đúng một lần”.

Mô hình thực tế cho nghiệp vụ quan trọng thường là **at-least-once delivery + idempotent consumer + local transaction + reconciliation**.

## 10. Vì sao ACK trước DB commit nguy hiểm?

~~~text
SAI:
  1. Consumer nhận ReserveStock
  2. ACK broker / commit offset
  3. Update inventory database
  4. Process chết ở bước 3
=> Broker tưởng đã xong nhưng tồn kho chưa được cập nhật.
~~~

Một quy trình có cơ sở an toàn hơn:

~~~text
  1. Nhận ReserveStock(commandId)
  2. Bắt đầu local transaction
  3. Kiểm tra processed command ID
  4. Nếu mới: áp dụng invariant, ghi state, inbox, outbox
  5. Commit transaction
  6. ACK broker hoặc commit offset
~~~

Nếu crash giữa bước 5 và 6, broker có thể giao lại. Consumer phải nhận diện command đã xử lý để không giữ hàng lần thứ hai. Với Kafka commit offset là tiến độ theo partition; với RabbitMQ basic.ack xác nhận delivery trên channel. Cần hiểu đúng primitive của nền tảng và framework trước khi cấu hình.

### 10.1. Idempotency tại business operation

Ví dụ ReserveStock được giao lại với cùng commandId. Consumer có thể dùng bảng processed_commands có UNIQUE(command_id), hoặc một business operation key như orderId + reservationAttempt.

~~~sql
BEGIN;

INSERT INTO processed_commands (command_id)
VALUES ('cmd-reserve-771')
ON CONFLICT DO NOTHING;

-- Chỉ khi đây là lần insert đầu mới áp dụng
-- invariant và cập nhật reservation, rồi ghi outbox.

COMMIT;
~~~

Đoạn SQL minh họa ý tưởng, không phải thuật toán hoàn chỉnh tự chạy: application phải dựa vào kết quả insert và kiểm soát concurrent transaction/locking. Không dùng một thao tác SELECT kiểm tra trùng rồi INSERT không có unique constraint, vì hai worker có thể cùng đi qua.

### 10.2. Với side effect bên ngoài database

Gửi email, capture payment và gọi hệ thống thứ ba không tự nằm trong local transaction của inbox. Cần operation key ổn định, trạng thái công việc, idempotency của downstream nếu có và reconciliation khi response bị mất. Inbox chỉ giúp tránh một số lần xử lý trùng ở local state; **không tự tạo exactly-once toàn hệ thống**.

## 11. Retry, backoff và DLQ/DLT

Một consumer có thể gặp các trường hợp khác nhau:

| Tình huống | Cách xử lý |
| --- | --- |
| Database tạm lỗi | Retry có backoff, jitter, giới hạn |
| HTTP downstream timeout | Retry nếu idempotent hoặc có cơ chế tra kết quả |
| Không đủ tồn kho | Business rejection, không retry kỹ thuật vô hạn |
| Message schema không parse được | Quarantine/DLQ, cảnh báo, sửa rồi replay |
| Event version đã cũ | Bỏ qua hoặc đối chiếu trạng thái theo policy |
| Message trùng ID | Không nhân side effect, hoàn tất idempotently |
| Consumer bị kill giữa xử lý | Redelivery và kiểm soát transaction |
| Event tới sai thứ tự | Version/sequence, chờ/fetch nguồn authoritative |
| Backlog tăng cao | Backpressure, scale, giới hạn in-flight, tối ưu DB |
| Broker outage | Producer/outbox retry, consumer reconnect, theo dõi SLA |

Poison message là thông điệp làm handler lỗi lặp lại (ví dụ schema không hợp lệ). Nếu chỉ retry vô hạn, một partition hoặc queue có thể bị kẹt. Cần retry budget, DLQ/DLT và quy trình xử lý/replay có trách nhiệm. DLQ không có nghĩa lỗi đã được giải quyết.

### 11.1. Trả kết quả command khác với retry delivery

Ordering gửi ReserveStock nhưng Inventory xác định không đủ hàng. Đây là **kết quả nghiệp vụ**; Inventory có thể phát ReservationRejected để saga quyết định CancelOrder. Không nên ném exception và cứ để broker giao lại như thể Inventory bị lỗi kỹ thuật.

## 12. Thứ tự và partition key

Giả sử Ordering phát:

~~~text
OrderPlaced(orderId=1001, version=1)
OrderConfirmed(orderId=1001, version=2)
OrderCancelled(orderId=1001, version=3)
~~~

Nếu Analytics nhận OrderCancelled rồi lại xử lý OrderPlaced cũ mà không kiểm tra version, projection có thể lùi trạng thái.

Kafka có thứ tự theo partition, không theo toàn topic nhiều partition. Với các event cùng orderId cần ordering, dùng key ổn định và thiết kế producer theo thứ tự logic. Tuy vậy, retry, nhiều producer, thay đổi partition count và replay vẫn khiến consumer cần xét aggregateVersion.

Một số key phù hợp:

| Nghiệp vụ | Key | Điều phải cân nhắc |
| --- | --- | --- |
| Order events | orderId | Giữ thứ tự theo Order; hot Order |
| Account balance | accountId | Cạnh tranh update và transaction |
| Product updates | productId | Version của Product |
| Per-tenant order | tenantId + orderId | Scope ID và phân bổ tải |
| Metrics không cần thứ tự theo entity | phân bổ đều | Yêu cầu aggregation và replay |

Tăng số consumer chỉ giúp xử lý song song khi broker có các đơn vị chia việc tương ứng. Nó không giải quyết một key nóng hoặc write lock tại database.

## 13. Ví dụ Java với Kafka

Dùng Spring Kafka để minh họa việc các ứng dụng có group riêng. Type OrderPlacedEvent và các service được dùng trong ví dụ cần có định nghĩa tương ứng ở dự án; serializer, transaction và error handler phụ thuộc môi trường.

### 13.1. Producer gửi một event

~~~java
@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderPlacedEvent> kafka;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderPlacedEvent> kafka) {
        this.kafka = kafka;
    }

    public CompletableFuture<SendResult<String, OrderPlacedEvent>> publish(
            OrderPlacedEvent event) {
        // Key theo orderId để hỗ trợ ordering theo Order
        // theo chính sách partitioner hiện hành.
        return kafka.send("order-events", event.orderId(), event);
    }
}
~~~

Future báo kết quả publish với broker theo producer configuration. Nó không chứng minh Analytics hay Notifications đã xử lý. Khi Order được lưu ở database, nên publish từ bản ghi outbox đã commit hoặc có cơ chế bảo đảm tương đương để tránh mất event.

### 13.2. Analytics consumer

~~~java
@Component
public class OrderAnalyticsConsumer {
    private final AnalyticsProjection projection;

    public OrderAnalyticsConsumer(AnalyticsProjection projection) {
        this.projection = projection;
    }

    @KafkaListener(
        topics = "order-events",
        groupId = "analytics-order-projection"
    )
    public void onOrderPlaced(OrderPlacedEvent event) {
        projection.applyIfNew(event);
    }
}
~~~

Dùng inbox/idempotency và transaction ở projection.applyIfNew; khi nhận lại cùng eventId, không cộng doanh thu lần thứ hai.

### 13.3. Notifications consumer dùng group riêng

~~~java
@Component
public class OrderNotificationConsumer {
    private final NotificationWorkflow workflow;

    public OrderNotificationConsumer(NotificationWorkflow workflow) {
        this.workflow = workflow;
    }

    @KafkaListener(
        topics = "order-events",
        groupId = "order-notifications"
    )
    public void onOrderPlaced(OrderPlacedEvent event) {
        workflow.enqueueReceiptIfNew(event.eventId(), event.orderId());
    }
}
~~~

Hai listener có group khác nhau, vì Analytics và Notifications đều cần nhận sự kiện. Nếu cả hai dùng chung group, một số partition có thể chỉ được một ứng dụng đọc. Nếu Notifications có thêm replica, các replica phải cùng group để chia tải.

Cấu hình commit offset, error handler, transaction và DLT phải theo hợp đồng cụ thể; đoạn mã không tạo những bảo đảm đó tự động.

## 14. Ví dụ với RabbitMQ và competing consumers

Một exchange route cùng event tới hai queue:

~~~text
exchange: orders.events
  -> queue: analytics.order-placed
        analytics-worker-1
        analytics-worker-2
  -> queue: notify.order-placed
        notify-worker-1
        notify-worker-2
~~~

Ví dụ listener:

~~~java
@Component
public class AnalyticsQueueConsumer {
    private final AnalyticsProjection projection;

    public AnalyticsQueueConsumer(AnalyticsProjection projection) {
        this.projection = projection;
    }

    @RabbitListener(queues = "analytics.order-placed")
    public void onMessage(OrderPlacedEvent event) {
        projection.applyIfNew(event);
    }
}
~~~

Cấu hình queue/exchange/binding, persistent message, publisher confirm, manual/auto ACK, prefetch, dead-letter exchange và retry policy cần được định nghĩa ngoài mã minh họa. Khi consumer throw lỗi, không nên giả định framework tự retry đúng số lần; nếu requeue vô hạn sẽ gây retry storm.

### 14.1. So sánh Kafka và RabbitMQ queue cổ điển

| Chủ đề | Kafka | RabbitMQ queue cổ điển |
| --- | --- | --- |
| Storage | Append-only partitioned log | Queue với delivery/ACK |
| Fan-out | Nhiều group đọc cùng topic | Nhiều queue bind vào exchange |
| Load sharing | Nhiều consumer cùng group chia partition | Nhiều worker cùng queue |
| Consumer progress | Offset theo group/partition | ACK/NACK delivery |
| Replay | Đọc offset cũ nếu record còn retention | ACK xong message thường không còn trong queue |
| Ordering | Theo partition | Bị ảnh hưởng bởi nhiều worker và redelivery |
| Scale | Giới hạn assignment bởi partition count | Giới hạn queue throughput, prefetch, broker và worker |
| Consumer failure | Reassignment, redelivery theo offset | Requeue/redelivery theo ACK |

RabbitMQ Streams và các Kafka pattern nâng cao có hành vi riêng; quyết định kiến trúc phải dựa vào đúng loại topic/queue và phiên bản chạy production.

## 15. Backpressure, throughput và consumer lag

Giao tiếp bất đồng bộ cho phép hấp thụ đột biến bằng backlog, nhưng backlog không thể tăng mãi:

- Nếu producer phát nhanh hơn tổng tốc độ xử lý, độ trễ tăng.
- Kafka consumer lag lớn kéo dài có thể báo consumer không bắt kịp, hot partition hoặc lỗi.
- RabbitMQ queue depth và unacked tăng có thể báo thiếu worker, downstream chậm hoặc prefetch quá cao.
- Khi retry thất bại nhiều lần, DLQ/DLT và CPU broker có thể tăng nhanh.
- Nếu record hết retention trước khi consumer đọc, một phần dữ liệu không thể replay từ broker.

Các biện pháp: scale instance trong giới hạn partition/queue, tối ưu database, batching phù hợp, giảm payload, kiểm soát concurrent calls, đặt quota/backpressure và theo dõi thời gian xử lý nghiệp vụ.

Không nên autoscale chỉ theo CPU. Một consumer có thể rảnh CPU nhưng chờ DB lock; thêm replica chỉ tăng cạnh tranh. Cần quan sát lag, processing time, error và broker throughput cùng lúc.

## 16. Consumer group trong Kubernetes

Ví dụ deployment ba replica Analytics:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-analytics
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-analytics
  template:
    metadata:
      labels:
        app: order-analytics
    spec:
      containers:
        - name: worker
          image: example/order-analytics:1.0.0
          env:
            - name: KAFKA_GROUP_ID
              value: analytics-order-projection
~~~

Ba pod dùng cùng group ID. Với Kafka topic hai partition, một pod có thể không được gán partition. Trong rolling update, phiên bản cũ và mới cùng group có thể tồn tại trong cửa sổ ngắn, nên phải giữ hợp đồng event tương thích.

YAML chỉ minh họa, chưa bao gồm secret, resources, health probes và cấu hình mạng cần thiết cho triển khai thật. Pod cần graceful shutdown để tránh commit offset khi công việc chưa xong. Với event xử lý dài, cần cấu hình poll/heartbeat và chia nhỏ công việc để tránh rebalance không cần thiết.

## 17. Bảo mật và giới hạn quyền

Broker là nơi dữ liệu đi qua nhiều service; cần thiết kế kiểm soát:

1. Producer chỉ có quyền publish topic/exchange cần thiết.
2. Consumer chỉ đọc nguồn cần thiết, không tự có quyền admin.
3. Identity và TLS phù hợp, credential được lưu qua secret manager.
4. ACL giới hạn topic, queue, consumer group hoặc namespace tùy nền tảng.
5. Payload tránh lộ token, dữ liệu thanh toán, thông tin cá nhân không cần thiết.
6. Log/trace không ghi full raw payload nhạy cảm.
7. DLQ, replay, backup và retention cũng được kiểm soát quyền và thời gian lưu.
8. Schema registry và tooling quản trị phải có owner và audit.

Không nên cấp cùng một principal admin cho mọi producer/consumer chỉ để tiết kiệm cấu hình. Quyền truy cập cũng là một phần ranh giới dịch vụ.

## 18. Quan sát từng mốc trong một luồng

Một trace tốt có thể liên kết:

~~~text
traceId: checkout-888

Ordering:
  Order committed
  outbox eventId=evt-order-1001-v1

Producer:
  published to order-events
  broker confirmed partition=2 offset=144

Analytics group:
  consumer analytics-2 received eventId
  projection committed
  offset advanced

Notifications group:
  consumer notify-1 received eventId
  email job queued
  provider delivery pending
~~~

Các chỉ số quan trọng:

| Lớp | Metric cần xem |
| --- | --- |
| Producer | Publish rate, error, retry, outbox backlog/age, ACK latency |
| Broker | Throughput, connection, replication, storage, disk/memory, queue depth |
| Consumer | Processing time, failures, duplicate count, lag, retry, DLQ |
| Group | Member count, rebalance count/duration, partition assignment |
| Nghiệp vụ | Thời gian hoàn tất order, email gửi, số workflow kẹt |

CorrelationId kết nối các thông điệp cùng workflow; causationId cho biết request/command/event trực tiếp dẫn đến bản tin. Timestamp giữa nhiều máy không bảo đảm sắp xếp nhân quả tuyệt đối.

## 19. Các lỗi thiết kế thường gặp

**Lỗi 1 — Dùng một consumer group cho các chức năng khác nhau.** Analytics và Notifications chia partition, mỗi bên thiếu event. Cần group riêng nếu cả hai cần toàn bộ luồng.

**Lỗi 2 — Mỗi replica một group ID.** Ba pod Notifications nhận cùng event và có thể gửi ba email. Dùng cùng group cho các replica chia tải.

**Lỗi 3 — Đồng nhất broker ACK với business completed.** Producer được ACK nhưng consumer còn backlog hoặc bị lỗi. Dùng operation status/event kết quả từ owner.

**Lỗi 4 — ACK trước DB commit.** Consumer crash và mất message chưa thực thi. Commit state trước ACK, kết hợp idempotency.

**Lỗi 5 — Tin consumer không bao giờ nhận trùng.** Redelivery sau crash, timeout hoặc rebalance có thể xuất hiện. Dùng message ID/business key và unique constraint.

**Lỗi 6 — Một queue cho mọi app cần fan-out.** Analytics và Audit cùng một RabbitMQ queue, mỗi bên chỉ nhận một phần message. Dùng queue/binding riêng.

**Lỗi 7 — Thêm consumer vượt số partition.** Không tăng throughput vì nhiều instance rảnh. Đánh giá partition count và key skew.

**Lỗi 8 — Mọi message lỗi đều retry vô hạn.** Schema sai có thể chặn partition/queue. Dùng classification, bounded retry, DLQ/DLT và replay.

**Lỗi 9 — Không version schema.** Producer đổi field/semantics khiến consumer cũ parse sai. Tạo contract, compatibility tests và thời hạn deprecation.

**Lỗi 10 — Consumer sửa dữ liệu owner khác.** Analytics viết vào bảng Order của Ordering. Giữ ranh giới sở hữu, cần thay đổi thì gửi command cho owner.

**Lỗi 11 — Bỏ qua ordering.** Event version 1 đến sau version 3 khiến projection bị lùi. Sử dụng business key và version/state guard.

**Lỗi 12 — Chuyển command thành event mơ hồ.** OrderNeedsPayment được broadcast nhưng không ai chịu trách nhiệm kết quả. Nếu cần Payments thực thi, thiết kế command có owner, timeout và kết quả.

**Lỗi 13 — Không giám sát retention.** Consumer offline quá lâu, offset bị xóa nhưng team tưởng có thể replay toàn bộ. Thiết kế nguồn backfill/khôi phục độc lập nếu dữ liệu quan trọng.

**Lỗi 14 — Chỉ scale consumer mà không scale dependency.** Các worker mới cùng chờ một database hay API rate limit. Tối ưu và giới hạn concurrency end-to-end.

## 20. Checklist thiết kế một luồng bất đồng bộ

Trước khi tạo topic/queue và triển khai consumer:

1. **Semantic:** đây là command hay event? Ý nghĩa cụ thể là gì?
2. **Owner:** service nào có quyền phát fact hoặc thực thi command?
3. **Producer:** ai gửi? Sự kiện được tạo sau commit nào?
4. **Destination:** topic, queue hay exchange? Routing/partition key nào?
5. **Groups/subscriptions:** những chức năng nào cần thấy mọi message? Những instance nào chỉ chia việc?
6. **Durability:** broker ACK và retention/replication bảo đảm phạm vi nào?
7. **Ordering:** có cần theo business key/aggregateVersion không?
8. **Processing:** consumer xử lý trong local transaction nào?
9. **Idempotency:** unique business key hoặc messageId nào ngăn side effect trùng?
10. **ACK/offset:** chỉ đánh dấu tiến độ khi nào?
11. **Retry/DLQ:** lỗi tạm, lỗi vĩnh viễn và business rejection được xử lý khác nhau chưa?
12. **Scale:** partition/queue throughput và downstream bottleneck có được tính?
13. **Compatibility:** producer mới/consumer cũ có hiểu schema và semantics trong rollout?
14. **Observability:** có đo producer error, consumer lag, rebalance, DLQ, business latency?
15. **Recovery:** nếu hết retention hoặc mất dữ liệu consumer có backfill thế nào?
16. **Security:** ACL, credential, quyền đọc lịch sử và dữ liệu nhạy cảm?
17. **Shutdown:** khi worker chết/rebalance có replay an toàn?
18. **Business outcome:** ai xác nhận hoàn tất, từ chối, hoặc cần compensation?

Checklist nên được lưu cùng thiết kế contract và vận hành để team biết phải xử lý sự cố ở producer, broker, consumer hay group.

## 21. Bài tập áp dụng: OrderPlaced cho ba ứng dụng

Một hệ thống có yêu cầu:

- Ordering phải phát OrderPlaced khi tạo đơn thành công.
- Analytics cần mọi event để tính doanh thu, có năm worker.
- Notifications cần mọi event để gửi email theo chính sách, có hai worker.
- Fraud cần mọi event để đánh giá rủi ro, có một worker.
- Khi Analytics ngừng 20 phút phải bắt kịp nếu còn dữ liệu theo retention.
- Lỗi của một subscriber không được chặn Ordering.
- Một event được redeliver cũng không được nhân đôi tác động.

**Thiết kế Kafka:**

~~~text
Topic order-events: 6 partitions

Group analytics-orders: A1 A2 A3 A4 A5
Group notify-orders:    N1 N2
Group fraud-orders:     F1

Mỗi group có offset riêng.
~~~

**Thiết kế RabbitMQ queue cổ điển:**

~~~text
Exchange orders.events
  -> queue analytics.order-placed -> A1 A2 A3 A4 A5
  -> queue notify.order-placed    -> N1 N2
  -> queue fraud.order-placed     -> F1
~~~

Câu hỏi cần trả lời:

- Nếu Analytics tăng lên bảy worker nhưng Kafka topic chỉ sáu partition, worker thứ bảy làm gì?
- Nếu Analytics và Notifications dùng cùng group ID, message sẽ đi đâu?
- Nếu Notification đã gửi email nhưng crash trước ACK, làm sao không gửi trùng?
- Nếu Analytics offline lâu hơn Kafka retention, có thể replay từ broker nữa không?
- Nếu một event sai schema, làm sao cô lập nó mà không gây retry vô hạn?
- Nếu OrderCancelled(version 3) được xử lý trước OrderPlaced(version 1), projection phải phản ứng thế nào?
- Nếu muốn chạy một nhóm Analytics V2 shadow để so sánh, phải đặt group/queue và side effects ra sao?

Đáp án cốt lõi: ba **đơn vị tiêu thụ độc lập** để fan-out, các instance trong từng đơn vị để chia tải, producer có outbox, consumer có idempotency, retry/DLQ và recovery. Broker vận chuyển; business owner quyết định trạng thái nghiệp vụ.

## 22. Câu hỏi ôn tập

1. Producer làm gì và vì sao producer ACK không chứng minh consumer đã xử lý?
2. Broker là nơi thực thi nghiệp vụ hay hạ tầng định tuyến/lưu message?
3. Consumer khác consumer group ở điểm nào?
4. Hai service khác nhau dùng cùng Kafka group ID có nguy cơ gì?
5. Vì sao mỗi replica của một service không nên tùy ý tạo group ID riêng?
6. Kafka partition và offset có tương đương RabbitMQ queue/ACK không?
7. Vì sao nhiều consumer hơn partition không tăng scale vô hạn?
8. Thế nào là fan-out, thế nào là competing consumers?
9. ACK trước khi commit và ACK sau khi commit có các rủi ro khác nhau ra sao?
10. At-least-once delivery ảnh hưởng gì đến việc thu tiền hoặc gửi email?
11. Khi nào cần transactional outbox và inbox/processed ID?
12. Event đến muộn hoặc sai thứ tự được xử lý bằng dữ liệu nào?
13. Consumer lag tăng có nhất thiết do thiếu CPU không?
14. Vì sao DLQ cần owner và quy trình replay?
15. Khi cần nhiều service đều xử lý một fact, cần bao nhiêu subscription logic?
16. Nếu event bị xóa do retention trước khi consumer đọc, có đường khôi phục nào?
17. Tại sao broker không thể thay thế business validation tại service owner?
18. Khi triển khai rolling update consumer group, cần kiểm tra những vấn đề tương thích nào?

---

**Ghi nhớ:** **Producer tạo và công bố** thông điệp; **broker tiếp nhận, lưu hoặc định tuyến** theo cơ chế của nó; **consumer đọc và xử lý** trong phạm vi mình sở hữu; **consumer group phối hợp chia tải** giữa các consumer cùng chức năng. Muốn nhiều ứng dụng đều nhận fact, tạo các subscription/group/queue độc lập. Muốn tăng tốc một ứng dụng, tăng worker trong cùng nhóm theo giới hạn partition/queue và downstream. Độ tin cậy đến từ việc hiểu đúng ACK/offset, transaction, idempotency, retention, retry, quan sát và recovery.