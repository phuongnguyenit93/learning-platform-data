# Xử lý gửi trùng và duy trì thứ tự cần thiết trong truyền sự kiện tin cậy

## 1. Mở đầu: cùng một sự kiện có thể đến hai lần, còn sự kiện mới có thể đến trước sự kiện cũ

Trong kiến trúc Microservices, **Ordering Service** công bố các sự kiện về đơn hàng. **Inventory**, **Payments**, **Notifications** và **Analytics** nhận sự kiện từ một message broker như Kafka, RabbitMQ hoặc nền tảng sự kiện tương đương.

Giả sử một đơn hàng ORD-1001 có quá trình:

~~~text
10:00:00 OrderPlaced      (order version 1)
10:00:05 OrderConfirmed   (order version 2)
10:00:10 OrderCancelled   (order version 3)
~~~

Ở phía consumer, thực tế có thể xảy ra:

~~~text
10:00:01 nhận OrderPlaced v1
10:00:06 nhận OrderConfirmed v2
10:00:07 nhận lại OrderConfirmed v2    <-- gửi trùng
10:00:11 nhận OrderCancelled v3
10:00:12 nhận trễ OrderConfirmed v2    <-- sự kiện cũ đến sau
~~~

Nếu consumer **gửi email xác nhận hai lần**, khách bị làm phiền. Nếu consumer **giảm tồn kho hai lần**, số lượng bị sai. Nếu bản chiếu đơn hàng **ghi đè CANCELLED thành CONFIRMED**, màn hình hiển thị trạng thái không đúng. Trong một workflow thanh toán, lỗi xử lý trùng hoặc sai thứ tự còn có thể tạo tác động tài chính nghiêm trọng.

Bài học này tập trung vào hai kỹ năng khác nhau nhưng thường phải kết hợp:

1. **Xử lý thông điệp trùng (duplicate delivery / duplicate processing):** một sự kiện hoặc một yêu cầu nghiệp vụ được giao lại nhưng không được gây tác dụng phụ thêm ngoài ý muốn.
2. **Duy trì thứ tự cần thiết (required ordering):** những sự kiện mà nghiệp vụ yêu cầu quan hệ trước–sau phải được áp trong phạm vi và theo luật rõ ràng, bất kể broker, mạng, retry hoặc consumer song song hoạt động thế nào.

Nguyên tắc cốt lõi là: **đừng giả định broker giao đúng một lần, đúng thứ tự toàn hệ thống; hãy xác định bảo đảm thực sự của từng tầng và bảo vệ bất biến ở consumer**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt duplicate publish, duplicate delivery, duplicate command và duplicate business operation.
- Giải thích at-most-once, at-least-once, exactly-once trong phạm vi cụ thể và giới hạn của các bảo đảm này.
- Thiết kế event envelope với eventId, aggregateId, aggregateVersion, operationId và correlationId.
- Sử dụng Transactional Outbox, consumer Inbox, unique constraint và idempotent state transitions.
- Chọn message key/partition key để duy trì thứ tự theo aggregate hoặc entity khi cần.
- Xử lý sự kiện trùng, cũ, đến trước, thiếu, bị retry, redelivery sau rebalance hoặc replay.
- Hiểu điểm cần lưu ý với Kafka partition/producer/consumer và RabbitMQ queue/ack/prefetch.
- Thiết kế ordering theo domain, không biến yêu cầu thứ tự của một Order thành total ordering đắt đỏ toàn bộ hệ thống.
- Xử lý các tác dụng phụ không dễ hoàn tác như charge, refund, email và gọi API bên ngoài.
- Vận hành, kiểm thử và quan sát event pipeline khi có lỗi thực tế.

## 2. Phân biệt bốn loại "trùng"

Không phải mọi lần nhìn thấy hai message đều có cùng nguyên nhân.

### 2.1. Producer phát lại cùng một event

Ordering đã commit OrderPlaced, gửi message nhưng không nhận được xác nhận từ broker vì mất kết nối. Producer retry gửi lại cùng một event.

~~~text
Ordering -> Broker: OrderPlaced(eventId=E-1)
Broker đã lưu E-1
ACK bị mất
Ordering -> Broker: OrderPlaced(eventId=E-1) lại
~~~

Tùy broker và producer configuration, log có thể chứa hơn một record đại diện cùng sự kiện logic. Kafka idempotent producer có thể giảm/loại một số duplicate do retry trong phạm vi producer session và partition theo cơ chế của Kafka, nhưng không thay thế quy tắc dedupe ở consumer cho mọi nguồn duplicate.

### 2.2. Broker giao lại sau khi consumer đã xử lý

Consumer nhận event và cập nhật database thành công, nhưng crash trước khi commit offset hoặc gửi ACK.

~~~text
Broker -> Consumer: E-1
Consumer -> DB: COMMIT business effect
Consumer crash trước ACK
Broker -> Consumer: E-1 lần nữa
~~~

Ở lần thứ hai, database đã có kết quả lần đầu. Nếu consumer không idempotent, tác dụng phụ sẽ lặp lại.

### 2.3. Hai message khác nhau yêu cầu cùng một hành động

Client retry POST /orders bằng key khác, tạo OrderPlaced(eventId=E-1) và OrderPlaced(eventId=E-2). Đây là **hai event khác ID** có thể cùng ám chỉ một thao tác người dùng.

Chỉ dedupe bằng eventId **không đủ**. Cần một **business operation ID/idempotency key** được bảo vệ ở nơi tạo đơn hoặc nơi thực hiện tác dụng phụ.

### 2.4. Hai events tương tự nhưng đều hợp lệ

Khách mua cùng một SKU hai lần trong hai đơn khác nhau. Hai event có payload gần giống nhưng là hai thao tác thật. Không được loại một event chỉ vì payload giống nhau.

**Kết luận:** phải chọn khóa định danh theo đúng cấp:
- eventId chống giao lại **cùng event**;
- operationId/idempotencyKey chống thực hiện lại **cùng yêu cầu nghiệp vụ**;
- aggregateId xác định **đối tượng nguồn**;
- aggregateVersion hoặc sequence hỗ trợ **thứ tự thay đổi**;
- correlationId giúp **liên kết luồng**, không tự là khóa chống trùng.

## 3. Bảo đảm giao message: at-most-once, at-least-once, exactly-once

| Thuật ngữ | Ý nghĩa khái niệm | Hậu quả cần quản lý |
| --- | --- | --- |
| **At-most-once delivery** | Không giao lại khi không biết xử lý thành công hay chưa; có thể mất message | Phải chấp nhận mất hoặc có cơ chế khôi phục khác |
| **At-least-once delivery** | Retry/redelivery giúp message có thể được xử lý, nhưng có thể đến nhiều lần | Consumer phải idempotent |
| **Exactly-once processing/effect** | Một tác động nhất định được quan sát một lần trong **phạm vi guarantee được định nghĩa** | Phải kiểm tra phạm vi storage, broker, external side effects |

Cụm từ “exactly once” dễ gây hiểu lầm nếu không xác định **cái gì** exactly once:

- Một record ghi lên một partition?
- Một phép biến đổi topic-to-topic trong Kafka transaction?
- Một lần cập nhật một bảng SQL?
- Một khoản thu tiền ngoài hệ thống?
- Một email đã được người nhận đọc?

Những phạm vi trên không tương đương.

### Ví dụ giới hạn của broker transaction

Một stream processor có thể dùng transaction của Kafka để liên kết việc đọc offset và ghi record đầu ra vào Kafka trong phạm vi hỗ trợ của Kafka. Điều đó **không tự đưa một database PostgreSQL độc lập hoặc cổng thanh toán bên ngoài vào cùng transaction**.

Do đó, ngay cả khi pipeline quảng bá exactly-once, lời gọi ChargePayment vẫn cần idempotency key ở Payment Service/provider và reconciliation khi kết quả không rõ.

### Tại sao at-least-once + idempotent consumer thường là điểm bắt đầu tốt?

Hệ thống có thể chấp nhận broker giao lại để tránh bỏ sót dữ liệu, sau đó consumer kiểm tra một ID ổn định và cập nhật state bằng transaction/constraint bảo đảm không gây side effect trùng. Đây là thiết kế rõ ràng hơn giả định rằng hạ tầng sẽ ngăn mọi duplicate thay cho ứng dụng.

## 4. Thứ tự là một quan hệ có phạm vi, không phải một con số toàn cục

Một thứ tự cần thiết thường liên quan đến **một aggregate hoặc một nhóm thực thể**.

Ví dụ cần đảm bảo:

~~~text
Order ORD-1001:
  OrderPlaced(v1)
  OrderConfirmed(v2)
  OrderCancelled(v3)

Order ORD-1002:
  OrderPlaced(v1)
  OrderConfirmed(v2)
~~~

Thứ tự **trong mỗi Order** quan trọng để không đưa ORD-1001 từ CANCELLED quay lại CONFIRMED. Nhưng Order ORD-1002 không nhất thiết phải chờ ORD-1001 hoàn tất.

Đó là **per-aggregate ordering** thay vì global total ordering.

### Các phạm vi hay gặp

| Phạm vi | Ví dụ | Có thực sự cần? |
| --- | --- | --- |
| Một aggregate | Thay đổi trạng thái của ORD-1001 | Thường có |
| Một customer | Cập nhật điểm thưởng theo customerId | Có thể có, tùy mô hình |
| Một account/ledger | Giao dịch cần bảo vệ số dư | Có thể cần serialization/transaction cụ thể |
| Một partition | Thứ tự log trong một Kafka partition | Bảo đảm của log, không tự là thứ tự xử lý thành công |
| Một topic nhiều partition | Mọi Order trên toàn topic | Thường không cần và không được mặc định bảo đảm |
| Nhiều topic/context | OrderPlaced trước PaymentSucceeded ở các topic khác nhau | Không có total order mặc định |
| Toàn hệ thống | Mọi message từ mọi service theo một thứ tự | Rất đắt và thường không cần |

Hãy bắt đầu từ câu hỏi: **hai sự kiện nào nếu đảo thứ tự sẽ gây ra kết quả nghiệp vụ sai?** Sau đó xác định entity/key và cơ chế bảo vệ tương ứng.

## 5. Một envelope cho sự kiện đáng tin cậy

Ví dụ:

~~~json
{
  "eventId": "evt-order-0003",
  "eventType": "OrderCancelled",
  "eventVersion": 1,
  "sourceContext": "Ordering",
  "aggregateType": "Order",
  "aggregateId": "ORD-1001",
  "aggregateVersion": 3,
  "operationId": "cancel-ORD-1001-01",
  "correlationId": "checkout-1001",
  "causationId": "cmd-cancel-1001",
  "occurredAt": "2026-11-11T10:00:10Z",
  "data": {
    "orderId": "ORD-1001",
    "reasonCode": "CUSTOMER_REQUEST"
  }
}
~~~

Ý nghĩa:

- **eventId** nhận diện sự kiện logic, phải giữ ổn định nếu cùng event được publish lại.
- **eventType** và **eventVersion** cho biết contract để consumer hiểu payload.
- **sourceContext** nêu context sở hữu dữ liệu và quyền công bố.
- **aggregateId** là đối tượng nguồn cần giữ ordering.
- **aggregateVersion** tăng theo commit của aggregate nguồn, nếu hệ thống chọn mô hình này.
- **operationId** nhận diện thao tác gây ra thay đổi, hữu ích khi client retry.
- **correlationId** liên kết một quy trình như checkout.
- **causationId** tham chiếu command/event đã kích hoạt sự kiện.
- **occurredAt** là timestamp dùng audit; không tự chứng minh thứ tự toàn hệ thống.
- **data** chứa trạng thái/thông tin nghiệp vụ được công bố theo contract.

Không có một envelope bắt buộc cho mọi dự án. Quan trọng là field semantics và tính ổn định khi retry. Một broker message có key, headers, offset riêng; chúng không mặc định thay thế eventId hoặc aggregateVersion.

### Phân biệt ID đặc biệt quan trọng

Hai sự kiện khác nhau của cùng Order có chung aggregateId nhưng eventId khác nhau. Một lần gửi lại đúng cùng event phải giữ eventId. Nếu producer tạo eventId mới mỗi lần retry một outbox record, dedupe theo eventId sẽ thất bại.

## 6. Nguồn sự kiện và Transactional Outbox

Một producer thường gặp bài toán **dual write**: ghi database nghiệp vụ và gửi message qua broker.

### Cách không an toàn

~~~text
BEGIN
UPDATE orders SET status='CONFIRMED'
COMMIT

publish OrderConfirmed
~~~

Nếu service crash sau commit nhưng trước publish, các consumer không biết Order đã CONFIRMED.

Ngược lại, publish trước commit có thể làm consumer nhận OrderConfirmed rồi transaction Order rollback.

### Transactional Outbox

Trong một local DB transaction:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED', version = version + 1
WHERE order_id = 'ORD-1001' AND version = 1;

INSERT INTO outbox_events (
    event_id, aggregate_type, aggregate_id,
    aggregate_version, event_type, payload, created_at
) VALUES (
    'evt-order-0002', 'Order', 'ORD-1001',
    2, 'OrderConfirmed', '{"orderId":"ORD-1001"}', NOW()
);

COMMIT;
~~~

Outbox publisher hoặc một CDC connector đọc những bản ghi đã commit và đưa lên broker.

### Outbox giúp gì?

- Gắn việc thay đổi state và lưu ý định phát event trong một transaction cục bộ.
- Cho phép tiếp tục publish sau producer restart.
- Có thể kiểm tra backlog và độ trễ phát event.
- Giảm nguy cơ một thay đổi nghiệp vụ đã commit nhưng mất thông báo liên quan.

### Outbox không giúp gì tự động?

- Không bảo đảm consumer chỉ thấy một lần.
- Không tự bảo đảm thứ tự nếu nhiều publisher xử lý outbox song song không có quy tắc.
- Không mở transaction xuyên Inventory, Payments và broker.
- Không bảo vệ business side effect khi client gửi trùng hai command.
- Không chứng minh tất cả consumer đã áp event.

Thiết kế Outbox phải kết hợp **ID ổn định, ordering strategy, publish checkpoint và idempotent consumer**.

## 7. Consumer Inbox: chống giao lại cùng event

Một cách thông dụng là bảng ghi sự kiện đã xử lý:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Mỗi logical consumer khác nhau có thể xử lý cùng một event cho mục đích khác nhau. Vì vậy key thường có **consumer identity + eventId**, không đơn thuần chỉ eventId cho toàn hệ thống.

### Quy trình transaction

~~~text
receive event E-1
BEGIN
  INSERT (consumerName, eventId) vào inbox
  nếu duplicate:
      không áp lại business effect
  nếu insert thành công:
      validate domain state
      cập nhật business DB / projection
      ghi Outbox cho event mới nếu cần
COMMIT
ACK / commit offset
~~~

**Inbox và tác động nghiệp vụ phải nằm trong cùng transaction cục bộ hoặc có thiết kế nguyên tử tương đương.** Nếu lưu inbox trước rồi DB update thất bại, lần redelivery sau sẽ tưởng event đã xử lý và bỏ sót kết quả.

### Race condition khi có nhiều instance

~~~text
Consumer A nhận E-1
Consumer B cũng nhận E-1 do rebalance/retry

A: SELECT inbox không thấy E-1
B: SELECT inbox không thấy E-1
A: update trạng thái
B: update trạng thái
~~~

Chỉ dùng SELECT rồi quyết định bằng if là chưa đủ. Unique constraint/atomic INSERT trong DB giúp một bên thắng và bên kia phát hiện duplicate. Transaction isolation/lock và logic update vẫn phải phù hợp với use case.

## 8. Một consumer idempotent phải xử lý cả tác động phụ

Dedupe event có thể giúp ngăn cập nhật SQL lặp, nhưng còn email, RPC và lệnh gửi provider.

Ví dụ:

~~~text
on OrderConfirmed:
  INSERT inbox(E-2)
  UPDATE order_read_model
  sendEmail()
  COMMIT
~~~

Nếu email gửi thành công rồi transaction DB rollback, event redelivery có thể gửi email lần thứ hai. Nếu commit DB xong rồi mới email và process chết trước email, trạng thái ghi “đã xử lý” nhưng thông báo không được gửi.

### Tách intent ra Outbox

Một cách:

~~~text
BEGIN
  INSERT inbox(E-2)
  UPDATE read model
  INSERT notification_outbox(
      notificationId='order-confirmed-ORD-1001',
      template='order_confirmed',
      recipientRef='CUS-17')
COMMIT

Notification worker:
  send notification with stable idempotency reference where supported
  record provider response / retry
~~~

Không phải email provider nào hỗ trợ idempotency toàn diện. Với email, mục tiêu có thể là **at-least-once delivery với dedup nội bộ**, biết rằng việc gửi trùng vẫn có nguy cơ trong khoảng mơ hồ. Với payments, cần mạnh hơn: idempotency tại Payment Service/provider và reconciliation theo reference.

### Phân biệt “không lặp effect” và “chỉ gửi một lần”

Hệ thống có thể publish command nhiều lần nhưng đảm bảo cùng operationId không tạo hai reservation. Đó là bảo vệ **business effect** quan trọng hơn việc cố chứng minh chỉ có một packet/message được gửi.

## 9. Idempotent state transition

Một consumer không nhất thiết luôn cần một hàng inbox cho mọi event nếu phép chuyển trạng thái được thiết kế idempotent và versioned, nhưng phải chứng minh điều đó với tất cả side effects.

Ví dụ một projection lưu trạng thái cuối:

~~~sql
UPDATE order_projection
SET status = 'CANCELLED',
    source_version = 3
WHERE order_id = 'ORD-1001'
  AND source_version < 3;
~~~

Nếu event version=3 được giao lại, UPDATE sẽ không tác động thêm. Nếu version=2 đến sau, nó cũng không đưa trạng thái về CONFIRMED.

Nhưng nếu handler còn gửi email hoặc giảm tồn, một phép UPDATE 0 dòng không tự bảo đảm side effect đã được xử lý đúng hoặc không lặp. Có thể cần inbox/outbox hoặc một operation ledger riêng.

### Với các thao tác cộng dồn

~~~text
Không an toàn khi duplicate:
  reward_points = reward_points + 100
  stock_reserved = stock_reserved + 2
  money_captured = money_captured + 500000
~~~

Các phép cộng cần được bao quanh bởi business identity/unique constraint hoặc transaction ledger với ID duy nhất. Nếu event E-1 giao lại, phép cộng chỉ được thực hiện một lần cho đúng nghiệp vụ.

## 10. Chọn message key và partition key để duy trì thứ tự

Với Kafka, record có **key**. Producer partitioner thường dùng key để xác định partition theo quy tắc được cấu hình.

Ví dụ:

~~~text
topic: orders.events

key=ORD-1001  OrderPlaced(v1)
key=ORD-1001  OrderConfirmed(v2)
key=ORD-1001  OrderCancelled(v3)

key=ORD-1002  OrderPlaced(v1)
key=ORD-1002  OrderConfirmed(v2)
~~~

Đặt các event cùng Order vào cùng partition giúp tận dụng **thứ tự log của một partition** trong điều kiện producer, partition mapping và công bố event tuân thủ contract.

### Vì sao dùng orderId thay vì eventId?

Nếu key=eventId, các event của cùng Order có key khác nhau nên có thể vào các partition khác nhau. Khi đó consumer không được giả định chúng theo thứ tự v1 → v2 → v3.

Nếu key=orderId, cùng entity thường được gửi tới cùng partition trong cấu hình partitioner ổn định, cho phép consumer xử lý theo thứ tự log cho entity.

### Tại sao không dùng một partition cho toàn bộ topic?

Một partition có thứ tự log rõ ràng, nhưng mọi record phải đi qua cùng trục xử lý theo mô hình tiêu thụ tương ứng, gây giới hạn throughput/parallelism. Nếu business chỉ cần thứ tự **trong từng Order**, việc đặt mọi Order vào một partition là yêu cầu mạnh hơn cần thiết.

### Key là hợp đồng, không chỉ một tham số kỹ thuật

Đổi key từ orderId sang customerId có thể:

- đưa các sự kiện của một Order sang partition khác;
- thay thứ tự mà consumer từng kỳ vọng;
- ảnh hưởng cách compacted topic giữ bản ghi;
- thay phân phối tải và tạo hot partitions;
- thay consumer state store hoặc local cache.

Thay partition key cần review, migration và kiểm thử như thay đổi API contract quan trọng.

## 11. Kafka bảo đảm thứ tự đến mức nào?

Trong Kafka, **mỗi partition là một log có thứ tự theo offset**:

~~~text
Partition P2:
offset 150 -> OrderPlaced(v1, ORD-1001)
offset 151 -> OrderConfirmed(v2, ORD-1001)
offset 152 -> OrderCancelled(v3, ORD-1001)
~~~

Một consumer đọc P2 theo offset sẽ thấy thứ tự log đó. Tuy nhiên có các điều kiện và giới hạn:

1. **Không có total order mặc định giữa nhiều partitions**.
2. **Không có total order mặc định giữa nhiều topics**.
3. Log order không tự là **commit order của nghiệp vụ** nếu producer phát sai trình tự.
4. Khi consumer xử lý song song bất cẩn, **thứ tự hoàn tất DB update** có thể khác thứ tự poll.
5. Message redelivery/replay có thể khiến consumer nhìn lại event cũ.
6. Thay key hoặc tăng partitions có thể làm mapping key→partition khác đối với records tương lai tùy partitioner.
7. Nhiều producer cùng ghi cho một aggregate cần cơ chế xác định thứ tự nguồn; broker chỉ sắp theo thứ tự record được append vào partition.

Vì vậy, **bảo đảm của partition là cần nhưng không đủ** cho correctness của Order state machine.

### Offset không phải aggregateVersion

Offset 152 chỉ là vị trí trong P2; nó có thể chứa event của nhiều Orders. Offset không đồng nghĩa Order ORD-1001 đang ở version 152.

AggregateVersion=3 là con số do domain/source quy định và bảo vệ khi commit. Consumer có thể dùng nó để quyết định event cũ hay mới của một Order.

## 12. Cẩn thận khi tăng số partitions

Giả sử ban đầu topic có 4 partitions, key=ORD-1001 được đưa tới P1. Sau khi tăng lên 8 partitions, một số chiến lược hashing có thể ánh xạ key này sang P5 cho records mới.

Hệ quả:

~~~text
Before:
  ORD-1001 v1 -> P1
  ORD-1001 v2 -> P1

After partition expansion:
  ORD-1001 v3 -> P5
~~~

Nếu các partitions được tiêu thụ đồng thời, consumer có thể xử lý v3 trước v2 mặc dù producer tạo v2 trước. Không thể chỉ nói “same key means always same partition forever” mà không xem cấu hình và sự thay đổi số partitions.

### Các lựa chọn quản lý

- Giữ số partitions ổn định trong giai đoạn cần ordering chặt, tăng capacity qua chiến lược khác.
- Dùng custom partitioning/mapping ổn định nếu có thể chứng minh và vận hành phù hợp.
- Khi cần repartition, tạo topic mới và có quy trình chuyển dữ liệu/cutover.
- Thiết kế consumer chống stale events bằng aggregateVersion và reconciliation.
- Đánh giá hot keys, throughput và consumer assignment trước khi thay partition count.

Không có biện pháp nào miễn kiểm thử. Chính sách chọn partition còn phụ thuộc client/broker, format key và cấu hình cụ thể.

## 13. Kafka producer: idempotence, retry và thứ tự

Kafka producer có cơ chế **idempotent producer** để tránh duplicate do retry của producer trong phạm vi protocol hỗ trợ. Nó sử dụng thông tin producer identity và sequence để broker nhận biết những record lặp ở partition.

Để duy trì yêu cầu ordering khi retry, cần kiểm tra:

- enable.idempotence và cấu hình liên quan trong phiên bản client được dùng;
- acks phù hợp durability;
- max.in.flight.requests.per.connection và giới hạn tương thích với idempotence;
- retries/delivery timeout/request timeout;
- partitioner và key selection;
- delivery callback, error handling và behavior khi producer restart;
- thứ tự lấy record từ outbox và số publisher đồng thời.

**Không khẳng định mọi cấu hình producer đều có cùng guarantee.** Các giá trị mặc định và ràng buộc phiên bản Kafka có thể thay đổi; phải xác minh theo client/broker đang chạy.

### Idempotent producer không thay business dedup

Một service có thể tạo **hai eventId khác nhau** cho cùng một thao tác khi retry ở tầng application. Producer idempotence không thể biết hai event đó nên được gộp vì chúng là hai record logic khác nhau.

Nếu Ordering tạo hai OrderPlaced do client double click với hai transaction riêng, cần bảo vệ ở domain bằng idempotency key/unique constraint, không chỉ bật producer idempotence.

### Nhiều publisher đọc cùng Outbox

Nếu nhiều worker publish events của một aggregate song song, chúng có thể lấy v2 và v3 rồi gửi v3 trước v2. Broker sẽ lưu theo thứ tự nhận được, nhưng đó không còn đúng business order.

Cần thiết kế:
- outbox ordering theo aggregate/version;
- serialization hoặc locking phù hợp khi cùng aggregate;
- partitioning nhất quán;
- xử lý batch/parallelism không phá sequencing;
- consumer version guards để chống stale/out-of-order.

## 14. Kafka consumer: poll order khác processing completion order

Một consumer có thể poll các records theo offset tăng dần nhưng dispatch xử lý async:

~~~text
Poll:
  offset=151 v2 -> Worker A (DB chậm)
  offset=152 v3 -> Worker B (DB nhanh)

Completion:
  Worker B commit v3 trước
  Worker A commit v2 sau
~~~

Nếu không có condition/version, kết quả cuối có thể bị ghi đè về v2. **Broker ordering không cứu được logic application xử lý đồng thời thiếu guard**.

### Chiến lược xử lý

1. Xử lý tuần tự mỗi partition hoặc mỗi aggregate khi thao tác yêu cầu tuần tự nghiêm ngặt.
2. Cho phép song song giữa partitions/keys độc lập, không giữa các events mâu thuẫn của cùng aggregate.
3. Dùng versioned state machine/optimistic locking để chống ghi đè cũ.
4. Khi dùng async worker pool, partition/aggregate-aware work queues và offset acknowledgment cần tính đến record chưa xong.
5. Theo dõi work-in-flight và rebalance để không commit offset vượt qua record chưa áp bền vững.

Đặc biệt, **commit offset N+1** có thể khiến records trước đó bị bỏ qua sau crash nếu application đã giao nhiều work items mà chưa đợi chúng hoàn tất. Cần thiết kế checkpoint chỉ sau những bản ghi liên tiếp đã xử lý xong theo semantics của consumer.

## 15. RabbitMQ: thứ tự hàng đợi và việc xử lý thực tế

RabbitMQ có mô hình exchange, queue, consumer, delivery acknowledgment và prefetch. Các điều kiện về thứ tự khác Kafka vì đây không phải cùng một kiểu partitioned log.

Ví dụ một queue:

~~~text
Publisher -> Exchange -> Queue:
  M1, M2, M3
~~~

Một consumer nhận tuần tự với prefetch phù hợp có thể quan sát thứ tự delivery mong đợi. Nhưng nếu có **nhiều consumers**, các message có thể được phân phối cho những process khác nhau và hoàn tất không theo thứ tự gốc. Requeue/redelivery, priorities, concurrency và các tính năng queue khác cũng ảnh hưởng thứ tự quan sát.

### Các điểm cần thiết kế

- Consumer count và prefetch.
- Manual ACK sau durable update.
- Cách xử lý NACK/requeue khi message lỗi.
- DLQ và retry queues có làm message trở lại không đúng vị trí ban đầu?
- Có cần một consumer hoặc partition/queue theo key để serialize không?
- TTL, delayed retry, dead-letter và poison message behavior.
- Thứ tự **delivery** có quan trọng hay thứ tự **business effect** mới quan trọng?

Không mặc định RabbitMQ “FIFO tuyệt đối” trong mọi cấu hình. Nếu muốn giữ thứ tự cho một nhóm đối tượng, cần chọn topology, routing key và cơ chế xử lý tương ứng hoặc dùng version guard ở consumer.

## 16. Idempotency và ordering là hai vấn đề độc lập

Một event trùng không nhất thiết là event cũ, và một event cũ không nhất thiết là duplicate.

| Trường hợp | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Cùng eventId đến lại | E-2 v2 đến hai lần | Dedup/inbox; không lặp side effect |
| EventId khác, cùng operationId | E-2a và E-2b do client retry | Business operation dedup/unique constraint |
| Event v2 đến sau v3 | v3 đã áp, v2 đến trễ | Version guard; không đưa state lùi |
| Event v3 đến trước v2 | Vượt qua một thay đổi có ý nghĩa | Buffer/reconcile hoặc apply snapshot có guard |
| Event v5 đến nhưng thiếu v4 | Có khoảng trống sequence | Chọn strict gap check hoặc snapshot-based recovery |
| Event cùng payload cho hai Orders | Hai người đặt cùng SKU | Xử lý cả hai vì operation/entity khác nhau |
| Event cũ replay sau khi rebuild | Reprocess lịch sử | Chế độ rebuild và offset/ledger riêng có chủ đích |

Chỉ một cơ chế “seen event IDs” không đủ để giải quyết mọi tình huống.

## 17. State machine bảo vệ logic nghiệp vụ

Một Order có chuyển trạng thái hợp lệ:

~~~text
PENDING -> RESERVED -> CONFIRMED -> FULFILLING -> DELIVERED
    |          |
    v          v
 REJECTED   CANCELLED
~~~

Ví dụ, nếu Order đã DELIVERED thì nhận lại OrderConfirmed không có nghĩa chuyển về CONFIRMED. State machine ở domain/read model cần biết những transitions được phép.

Một mẫu SQL cập nhật có điều kiện:

~~~sql
UPDATE order_projection
SET status = 'CANCELLED',
    source_version = 3
WHERE order_id = 'ORD-1001'
  AND source_version < 3
  AND status IN ('PENDING', 'RESERVED', 'CONFIRMED');
~~~

Điều kiện là ví dụ; business thật có thể không cho hủy từ CONFIRMED khi shipment đã bàn giao, hoặc cần trạng thái CANCEL_REQUESTED. **Version là biện pháp bảo vệ stale write, state machine là biện pháp bảo vệ semantic transition**. Hai thứ bổ trợ nhau.

### Khi event cũ chứa dữ liệu bổ sung

Nếu event v1 chứa customerId còn event v3 không chứa, áp v3 trước và bỏ v1 hoàn toàn có thể làm projection thiếu customerId. Cần chọn một trong những thiết kế:

- event snapshot chứa đầy đủ trường cần cho projection;
- pending events cho đến khi đủ các version;
- nguồn dữ liệu đọc tách theo field/loại event;
- bootstrap snapshot rồi tiếp tục incremental events;
- reconciliation từ context có thẩm quyền.

Không được đơn giản nói “drop all smaller versions” nếu event không có snapshot semantics.

## 18. Strict ordering hay monotonic state?

Có ít nhất hai yêu cầu khác nhau:

**Strict in-order processing:** phải áp v1, rồi v2, rồi v3, vì mỗi delta phụ thuộc trạng thái của version trước.

**Monotonic update / latest-state wins với guard:** một snapshot trạng thái đầy đủ ở v3 có thể áp trực tiếp nếu nó chứa dữ liệu cần thiết; v2 đến sau bị bỏ.

### Ví dụ delta cần strict order

~~~json
{"eventType":"QuantityIncreased","aggregateVersion":2,"delta":5}
{"eventType":"QuantityDecreased","aggregateVersion":3,"delta":3}
~~~

Nếu consumer bỏ v2 vì thấy v3 trước, tổng có thể sai. Cần giữ/đòi sequence hoặc một snapshot authoritative. Với ledger tài chính, nên có mô hình transaction ledger và invariant thích hợp chứ không tùy tiện chỉ giữ số dư “mới nhất”.

### Ví dụ snapshot có thể skip version

~~~json
{"eventType":"OrderSnapshotUpdated","aggregateVersion":3,
 "data":{"status":"CANCELLED","totalMinor":500000,"currency":"VND"}}
~~~

Nếu contract cam kết message là snapshot đầy đủ của những field projection cần, việc nhận v3 trước v2 có thể cho phép cập nhật theo version mà không đòi phải áp mọi delta. Nhưng cần cẩn trọng với side effects gắn vào các event giữa các version.

**Lựa chọn strict ordering hay skip stale** phải theo semantics của event, không chỉ theo công nghệ broker.

## 19. Phát hiện khoảng trống sequence

Một consumer đang ở version=5, nhận event version=7:

~~~text
Expected: 6
Received: 7
Gap: version 6 chưa được nhìn thấy
~~~

Nếu event là delta và v6 quan trọng, không nên áp v7 rồi coi v6 đã được xử lý. Có thể:

1. Giữ event v7 trong pending store có TTL/giới hạn.
2. Tiếp tục chờ v6 trong phạm vi thời gian hợp lý.
3. Tra nguồn sự thật hoặc snapshot có version >=7.
4. Dùng backfill/replay nếu log còn giữ v6.
5. Cảnh báo/đưa vào luồng điều tra khi gap không thể khép lại.
6. Chỉ commit checkpoint tương ứng khi những semantics cần thiết đã được bảo toàn.

### Pending events không thể tăng vô hạn

Một partition thiếu v6 và nhận v7…v1000 có thể làm pending store phình to. Cần giới hạn số message, thời gian chờ, quota, cơ chế recovery và cảnh báo để không gây memory exhaustion.

## 20. Nhiều context nguồn không có một global version

Ordering phát OrderConfirmed(version=5), Payments phát PaymentSucceeded(version=4), Fulfillment phát ShipmentCreated(version=2). Những con số thuộc **các aggregate độc lập**.

~~~text
Order version 5
Payment version 4
Shipment version 2
~~~

Không thể kết luận Order event mới hơn Payment event vì 5 > 4.

Read model tổng hợp nên theo dõi tiến trình riêng:

~~~json
{
  "orderId": "ORD-1001",
  "orderStatus": "CONFIRMED",
  "paymentStatus": "SUCCEEDED",
  "shipmentStatus": "CREATED",
  "sourceVersions": {
    "ordering:ORD-1001": 5,
    "payments:PAY-101": 4,
    "shipping:SHIP-9": 2
  }
}
~~~

Từ đó, mỗi event cập nhật phần thuộc nguồn có thẩm quyền của mình. Một PaymentSucceeded đến trước OrderPlaced có thể được lưu trong PaymentProjection riêng hoặc pending store thay vì bị bỏ vì thiếu hàng Order.

**Global total order xuyên nhiều service** là một yêu cầu rất mạnh và thường không thể có một cách tự nhiên mà vẫn giữ autonomy; nếu business thật sự đòi một thứ tự chung, cần thiết kế coordinator/ledger/serialization boundary cụ thể và chấp nhận các trade-off.

## 21. Consumer xử lý song song nhưng vẫn giữ ordering theo key

Muốn throughput cao, không nhất thiết chạy mọi event tuần tự trên một worker. Có thể serialize **theo aggregateId** trong khi xử lý nhiều aggregates đồng thời.

~~~text
Partition / Key ORD-1001 -> Worker lane A:
  v1 -> v2 -> v3

Partition / Key ORD-1002 -> Worker lane B:
  v1 -> v2

Partition / Key ORD-1003 -> Worker lane C:
  v1 -> v2 -> v3 -> v4
~~~

Cần bảo đảm cùng aggregate được đưa vào cùng lane/lock logic trong thời gian xử lý và khi restart/rebalance. Với Kafka, consumer group partition assignment thường tạo một owner active cho một partition, nhưng code nội bộ vẫn có thể dispatch sang nhiều threads. Với RabbitMQ, có thể dùng sharding/routing-key queues theo chính sách.

### Vấn đề hot key

Một khách có hàng triệu cập nhật cùng customerId có thể trở thành key quá nóng, giới hạn throughput của lane đó. Cần cân nhắc:

- Thứ tự thực sự cần theo customerId hay theo orderId?
- Có thể tách aggregate thành các account/shard/sub-entities độc lập không?
- Có thể chuyển cập nhật cộng dồn sang mô hình ledger/transactional aggregation không?
- Có được phép xử lý commutative operations song song không?
- Có quy trình phân vùng lại và backfill an toàn không?

Không dùng key ngẫu nhiên để tăng throughput nếu điều đó phá yêu cầu thứ tự của cùng đối tượng.

## 22. Xử lý retry mà không phá thứ tự nghiệp vụ

Một consumer nhận v2 nhưng DB unavailable. Nếu consumer gửi v2 sang retry topic có delay, rồi tiếp tục xử lý v3 trên topic chính, v3 có thể hoàn tất trước v2.

~~~text
Main topic:
  v2 -> DB error -> delayed retry topic
  v3 -> processed successfully

Retry topic later:
  v2 -> arrives after v3
~~~

Với một state projection theo snapshot, version guard có thể an toàn. Với **delta**, v3 phụ thuộc v2 nên phải xử lý gap hoặc block/resume đúng chỗ.

### Những chiến lược thông dụng

**A. Retry tại chỗ với pause partition:** tạm dừng xử lý các records tiếp theo của partition khi v2 cần hoàn tất, có backoff và giới hạn. Ưu điểm giữ thứ tự, nhược điểm chặn mọi keys cùng partition.

**B. Parking lot theo aggregate:** đưa event lỗi và các events phụ thuộc của cùng key vào pending store. Các keys khác tiếp tục xử lý; cần logic version/checkpoint phức tạp.

**C. Retry topic có sequence guard:** cho phép retry ngoài luồng, nhưng consumer không áp v3 nếu v2 chưa hoàn tất theo yêu cầu business.

**D. Snapshot/reconciliation:** nếu từng event là state snapshot hoặc nguồn có API lấy trạng thái mới, có thể bỏ qua stale delta sau khi đã dựng một state hợp lệ từ snapshot có version.

**E. DLQ/quarantine:** áp dụng khi payload không thể xử lý; không có nghĩa được bỏ sequence gap vĩnh viễn mà không báo.

### Tại sao DLQ có thể tạo lỗ hổng thứ tự?

Nếu event v2 đưa vào DLQ và consumer tiếp tục với v3, log vẫn có thứ tự, nhưng business effects có thể thiếu v2. Phải quyết định có được phép bỏ v2 và cách tái đồng bộ trước khi tiếp tục.

## 23. ACK, offset và thời điểm ghi checkpoint

Trong at-least-once consumer:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Broker
    participant C as Consumer
    participant D as Business DB

    B-->>C: Deliver event E-1
    C->>D: BEGIN + dedupe + apply update
    D-->>C: COMMIT successful
    C->>B: ACK / commit offset
~~~

**ACK sau COMMIT** giúp bảo đảm nếu DB commit thất bại thì broker còn khả năng giao lại. Nhưng nếu consumer crash giữa COMMIT và ACK, sự kiện sẽ đến lại: đó là lúc idempotency phát huy tác dụng.

Nếu ACK/commit offset **trước** DB COMMIT, crash có thể làm event mất khỏi luồng xử lý bình thường. Một số framework có transaction integrations hoặc offset management khác; vẫn phải phân tích atomicity boundaries thực tế.

### Offset commit trong xử lý song song

Nếu record offset=10 đang chạy chậm nhưng offset=11 đã xong, commit offset sau 11 có thể bỏ qua 10 khi consumer restart. Cần commit theo một **contiguous processed prefix** hoặc cơ chế lưu checkpoint/recovery tương đương, không lấy “offset lớn nhất đã xong” một cách mù quáng.

## 24. Saga: không bù nhầm khi event trùng hoặc đến muộn

Trong checkout Saga:

~~~text
OrderPlaced -> ReserveStock -> StockReserved
            -> AuthorizePayment -> PaymentAuthorized
            -> ConfirmOrder
~~~

Một StockReserved đến lại không được tạo AuthorizePayment mới nếu Saga đã tiến đến bước khác. Một PaymentAuthorized đến sau khi Saga chuyển sang COMPENSATING không nên tự đưa đơn thành CONFIRMED.

Một Saga state machine cần:

- sagaId và bước đang chờ;
- expected operationId;
- eventId đã nhận;
- trạng thái của reservation/payment/compensation;
- version của Saga state;
- timeout/reconciliation status;
- local transaction + outbox cho command tiếp;
- rules khi late event đến.

Ví dụ:

~~~text
WAITING_FOR_PAYMENT + PaymentAuthorized(expected operationId)
    -> CONFIRMING_ORDER

WAITING_FOR_PAYMENT + PaymentRejected(expected operationId)
    -> RELEASING_STOCK

COMPENSATING + late PaymentAuthorized
    -> RECONCILE / VOID_OR_REFUND decision
    -> không tự CONFIRM_ORDER
~~~

**Không drop mọi late event vô điều kiện**, nhất là event xác nhận tiền đã thu. Nó có thể đòi bù hoặc xử lý thủ công.

## 25. Duplicate có thể xuất hiện sau replay hoặc rebuild

Một consumer rebuild read model có thể đọc lại events từ đầu:

~~~text
Production consumer: đã xử lý E-1 ... E-500
Rebuild consumer: đọc lại E-1 ... E-500
~~~

Nếu rebuild chỉ cập nhật read database v2 tách biệt, đây là hành vi có chủ đích. Nhưng nếu cùng listener gửi email hoặc gọi ChargePayment, replay có thể tạo side effects không mong muốn.

Cần phân biệt:

- **Operational redelivery:** cùng consumer thực thi lại message do ACK/offset.
- **Intentional replay:** chạy lại lịch sử để dựng projection hoặc tính toán lại.
- **Business re-execution:** người dùng thực sự yêu cầu một operation mới.

### Rebuild an toàn

1. Tách projector/read model mới khỏi các side-effect consumers.
2. Dùng consumer group/checkpoint riêng.
3. Giữ schema cũ, decoder và history đủ để replay.
4. Dùng event identity/version guard phù hợp.
5. Không lặp external calls như payment/email khi chỉ rebuild read store.
6. Catch up event mới và kiểm tra watermark trước cutover.
7. Đối chiếu số lượng records và business totals trước khi thay read model đang phục vụ.

Một event đã bị retention xóa có thể khiến rebuild không đủ dữ liệu; cần snapshot/backfill hoặc archive.

## 26. Cơ chế dedupe bằng database

Một pattern đơn giản:

~~~sql
CREATE TABLE operations (
    operation_scope VARCHAR(128) NOT NULL,
    operation_id VARCHAR(128) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    result_reference VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (operation_scope, operation_id)
);
~~~

Khi command ReserveStock đến:

1. Xác định operation_scope, ví dụ tenant + commandType.
2. Tìm/đăng ký operation_id trong transaction.
3. Nếu đã tồn tại và payload_hash khớp, trả kết quả của **cùng operation** hoặc trạng thái đang chạy.
4. Nếu đã tồn tại nhưng payload khác, trả conflict.
5. Nếu mới, kiểm tra business invariants và tạo reservation.
6. Ghi kết quả operation cùng durable state.
7. Publish outcome bằng outbox nếu cần.

### Vì sao phải có payload hash?

Một client có thể vô tình dùng lại key nhưng đổi quantity từ 2 thành 3. Nếu hệ thống lặng lẽ trả kết quả của lần quantity=2, người dùng có thể hiểu sai. Contract cần quy định same key + different payload là lỗi hoặc có quy tắc business cụ thể.

### Retention của dedupe ledger

Không được xóa operation_id trước khi các retry hợp lệ có thể quay lại, đặc biệt với payment provider callback trễ. Dedupe retention cần dựa vào business lifecycle, tối đa độ trễ và khả năng đối soát, không chỉ dùng TTL 10 phút cho mọi use case.

Đối với những tài nguyên tài chính quan trọng, unique business reference và ledger bền vững có thể cần tồn tại lâu hơn thời gian message broker retention.

## 27. Ví dụ SQL xử lý inbox và cập nhật projection trong một transaction

Mô hình PostgreSQL minh họa:

~~~sql
CREATE TABLE order_status_projection (
    order_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    source_version BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE projection_inbox (
    projector_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (projector_name, event_id)
);
~~~

Pseudo-flow cho một event:

~~~sql
BEGIN;

INSERT INTO projection_inbox (projector_name, event_id)
VALUES ('order-status-v1', 'evt-order-0003')
ON CONFLICT DO NOTHING;

-- Ứng dụng phải biết INSERT đã tạo mới 1 dòng hay 0 dòng.
-- Nếu 0: eventId trùng, không áp business update lần hai.
-- Nếu 1: chạy update có điều kiện theo state/version.

UPDATE order_status_projection
SET status = 'CANCELLED',
    source_version = 3,
    updated_at = NOW()
WHERE order_id = 'ORD-1001'
  AND source_version < 3;

COMMIT;
~~~

Đây là **minh họa khung xử lý**, không phải script thực thi tự động đầy đủ. Ứng dụng phải nối logic conditional insert với decision update trong cùng transaction. Với một event không tồn tại row, cần chiến lược tạo row hoặc pending theo semantics, không mặc định UPDATE 0 dòng là đã xử lý đầy đủ.

### Khi inbox insert thành công nhưng event không thể áp

Nếu handler nhận event version=7 nhưng yêu cầu version=6 mà chưa có, không nên đánh dấu “fully processed” rồi bỏ event. Có thể ghi trạng thái PENDING cùng event payload trong durable pending store; xác định rõ nghĩa của processed vs accepted vs applied và checkpoint strategy.

## 28. Java/Spring: consumer idempotent có version guard

Đoạn code minh họa cấu trúc, giả định các repository và model được ứng dụng định nghĩa:

~~~java
public record OrderStatusEvent(
    String eventId,
    String orderId,
    long aggregateVersion,
    String newStatus
) {}

@Service
public final class OrderStatusProjector {
    private final InboxRepository inbox;
    private final OrderProjectionRepository projection;

    public OrderStatusProjector(
        InboxRepository inbox,
        OrderProjectionRepository projection
    ) {
        this.inbox = inbox;
        this.projection = projection;
    }

    @Transactional
    public void apply(OrderStatusEvent event) {
        // insertIfAbsent cần được thực thi bằng unique constraint
        // trong cùng local transaction với projection update.
        boolean fresh = inbox.insertIfAbsent(
            "order-status-v1", event.eventId()
        );
        if (!fresh) {
            return;
        }

        // Repository phải kiểm tra version và transition rules.
        projection.applyIfNewerAndAllowed(
            event.orderId(),
            event.aggregateVersion(),
            event.newStatus()
        );
    }
}
~~~

Ví dụ listener Kafka:

~~~java
@Component
public class OrderEventListener {
    private final OrderStatusProjector projector;

    public OrderEventListener(OrderStatusProjector projector) {
        this.projector = projector;
    }

    @KafkaListener(
        topics = "orders.events",
        groupId = "order-status-v1"
    )
    public void onEvent(OrderStatusEvent event) {
        projector.apply(event);
        // Offset/ACK chỉ an toàn sau khi transaction DB hoàn tất.
        // Cần cấu hình consumer/container/error handler phù hợp.
    }
}
~~~

**Các interface, entity, serializer và cấu hình Spring Kafka không được trình bày đầy đủ**; đây là ví dụ ý tưởng cho sinh viên. Nếu event có semantics delta và đến thiếu version, repository phải từ chối/quarantine/đợi hoặc tái tạo, không chỉ dùng phép so sánh > rồi cho qua.

### Kiểm thử giả lập

~~~text
Event v1 đến: apply thành công
Event v1 đến lại: inbox duplicate, không tác động
Event v3 đến: nếu snapshot đủ, apply hoặc chờ v2 theo contract
Event v2 đến sau v3: stale, không đưa trạng thái lùi
Event v4 thuộc order khác: xử lý độc lập
DB crash trước COMMIT: event có thể redeliver và áp lại an toàn
DB COMMIT rồi crash trước ACK: inbox chặn side effect lặp
~~~

## 29. Phân biệt trạng thái "đã nhận", "đã áp", "đã phát tiếp"

Một pipeline có thể có nhiều mốc:

~~~text
Message received
   -> validated
   -> accepted / stored
   -> domain change applied
   -> outgoing event committed to outbox
   -> broker ACK
   -> downstream processed
~~~

Dùng từ **processed** mà không nêu mốc có thể tạo hiểu lầm. Ví dụ listener chỉ enqueue event vào một local memory queue rồi ACK broker không chứng minh kết quả đã được lưu bền vững; crash sau ACK sẽ mất công việc.

Nên ghi rõ telemetry và trạng thái:

- ACCEPTED: message đã được nhận/ghi durable inbox.
- APPLIED: thay đổi trong read/business DB đã commit.
- PUBLISHED: event tiếp theo đã được broker xác nhận theo policy.
- COMPLETED: workflow nghiệp vụ đạt trạng thái cuối theo authority.
- RECONCILING: kết quả chưa rõ, cần xác minh.
- QUARANTINED: event không thể xử lý tự động.

Các trạng thái trên chỉ là quy ước minh họa; mỗi hệ thống cần định nghĩa một lifecycle nhất quán.

## 30. Trường hợp payment: chống trùng chưa đủ nếu provider không chắc chắn

Giả sử Payment Service nhận ChargePayment(operationId=charge-ORD-1001):

~~~text
Payment Service -> Provider: POST charge
Provider đã charge thành công
Response bị mất
Payment Service timeout
Broker giao lại ChargePayment
~~~

Nếu Payment Service tạo provider idempotency key mới ở lần retry, có thể thu tiền hai lần.

Thiết kế phù hợp:

1. Payment Service lưu payment attempt với operationId duy nhất.
2. Provider request dùng **cùng provider idempotency reference** cho cùng attempt khi provider hỗ trợ.
3. Sau timeout, trạng thái được giữ UNKNOWN/PENDING cho đến khi xác minh.
4. Nếu provider hỗ trợ query by reference, tiến hành reconciliation.
5. Duplicate command cùng operationId không tạo payment attempt mới.
6. Event PaymentSucceeded được phát sau khi nguồn tài chính xác nhận semantics thích hợp.
7. Refund/void là **operation mới** với ID riêng và điều kiện nghiệp vụ rõ.

EventId dedup chỉ xử lý redelivery của một event; **business operation ledger** là cơ chế chính để chống double charge.

## 31. Trường hợp Inventory: không oversell khi hai consumer chạy đồng thời

Hai request khác nhau hợp lệ có thể cùng giữ chiếc hàng cuối cùng. Không thể chỉ dedupe event vì operationId khác nhau; cần atomic stock constraint.

~~~sql
UPDATE inventory_stock
SET available_qty = available_qty - 1,
    reserved_qty = reserved_qty + 1
WHERE sku = 'BOOK-01'
  AND available_qty >= 1;
~~~

Nếu 0 dòng ảnh hưởng, không đủ hàng hoặc trạng thái đã thay đổi; domain handler trả StockRejected theo đúng lý do. Cần lưu reservation row và operation ID trong transaction phù hợp để retry cùng operation không giữ hàng thêm.

**Khóa JVM synchronized** ở một instance không bảo vệ nhiều replicas. Transaction/constraint tại source authority mới xử lý việc cạnh tranh đồng thời.

### ReleaseStock cũng phải idempotent

Nếu Saga bù, ReleaseStock(reservationId=RES-1, operationId=release-RES-1) có thể đến hai lần. Chỉ được tăng available_qty một lần nếu reservation thực sự chuyển RESERVED → RELEASED. Có thể dùng update có điều kiện trên reservation status rồi cập nhật tồn trong cùng transaction.

## 32. Trường hợp Notifications: tránh gửi email trùng

Một email xác nhận được sinh từ OrderConfirmed. Broker có thể giao lại event, và provider email không nhất thiết hỗ trợ dedupe theo idempotency key.

Các biện pháp:

- Tạo notificationId ổn định theo (orderId, template, business trigger).
- Có unique constraint cho notification intent.
- Gửi qua outbox/worker với trạng thái SENDING/SENT/RETRY.
- Theo dõi provider message ID nếu có.
- Tránh enqueue hai notification intents khi cùng event redeliver.
- Nếu kết quả gửi không rõ sau timeout, hiểu rằng có thể gửi trùng nếu provider không có API xác minh/idempotency.
- Thiết kế template chịu được việc người nhận thấy hai thông báo hiếm hoi; không dùng email receipt làm bằng chứng một transaction tiền đã thành công.

Không hứa “email đúng một lần” nếu provider và cơ chế mạng không cung cấp bảo đảm đó.

## 33. Vì sao cố gắng duy trì global order có thể làm hệ thống kém hiệu quả?

Giả sử 10.000 đơn độc lập đều phải đợi một single-thread consumer vì nhóm đặt yêu cầu “mọi OrderPlaced phải theo thứ tự tuyệt đối”. Khi consumer xử lý chậm một Order, toàn bộ tiến trình sau bị chặn.

Trong phần lớn ứng dụng, business chỉ cần:

- Những thay đổi của **cùng Order** không bị áp lùi.
- Những giao dịch trên **cùng account** tuân thủ invariant số dư.
- Những reservations trên **cùng SKU/stock bucket** không vượt lượng tồn.
- Những events độc lập có thể được xử lý song song.

Các nhu cầu này cần cơ chế khác nhau. Không phải mọi invariant đều giải quyết bằng một Kafka partition: số dư ngân hàng có thể cần database serializable/ledger; stock cần atomic update; Order projection cần version guard; email cần stable notification identity.

**Giảm phạm vi ordering đến đúng business boundary** giúp hệ thống dễ scale, giảm hot spots và giảm nguy cơ một message lỗi chặn toàn bộ thông điệp không liên quan.

## 34. Hot partitions và throughput

Một số key tập trung quá nhiều message vào cùng partition. Ví dụ tất cả event của một tenant rất lớn dùng tenantId làm key. Nếu yêu cầu ordering thật chỉ theo orderId, dùng tenantId có thể tạo hot partition không cần thiết.

Cách xem xét:

1. Key distribution thực tế: số records/s theo key và partition.
2. Business invariant cần nhóm theo key nào.
3. Consumer group có bao nhiêu partitions và threads.
4. DB side effect có điểm tranh chấp chung khác không.
5. Có thể giảm kích thước message, batch và xử lý không đồng bộ mà vẫn giữ ordering không.
6. Nếu cần repartition, có kế hoạch migrate/checkpoint/version guard không.

Đừng thay key hay tăng partitions chỉ vì throughput mà chưa xét các event đang nằm trong log và ordering assumptions của consumer cũ.

## 35. Quan sát: đo duplicate và out-of-order một cách có ích

Một hệ thống “không lỗi HTTP” vẫn có thể âm thầm xử lý thiếu hoặc trùng event. Cần theo dõi các chỉ số:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Duplicates detected | Số lần inbox/operation ledger phát hiện trùng |
| Consumer lag | Message đang chờ theo partition/group |
| Max event age | Tuổi lớn nhất của event chưa áp |
| Out-of-order count | Event version cũ đến sau version mới hoặc gap |
| Sequence gaps pending | Số aggregate đang chờ version bị thiếu |
| Retry attempts | Lỗi transient và nguy cơ retry storm |
| DLQ/quarantine count | Event không thể xử lý tự động |
| Outbox pending age | Event commit ở source nhưng chưa publish |
| Projection source lag | Read model chậm hơn nguồn bao lâu |
| Business reconciliation mismatch | Kết quả tồn kho/thanh toán không khớp |
| Consumer rebalance/crash | Thời điểm dễ xuất hiện redelivery |
| Side-effect duplicate prevented | Thao tác trùng đã bị chặn bởi idempotency |

### Logs có cấu trúc

~~~text
service=order-projection consumer=order-status-v1
eventId=evt-order-0003 orderId=ORD-1001
aggregateVersion=3 processing=APPLIED

service=order-projection consumer=order-status-v1
eventId=evt-order-0003 orderId=ORD-1001
aggregateVersion=3 processing=DUPLICATE_SKIPPED

service=order-projection consumer=order-status-v1
eventId=evt-order-0002 orderId=ORD-1001
aggregateVersion=2 processing=STALE_EVENT_SKIPPED
~~~

Giữ eventId, operationId, orderId và correlationId trong logs theo chính sách bảo vệ dữ liệu. Không ghi token, số thẻ, password, credentials hoặc payload PII không cần thiết. Tránh dùng orderId/eventId làm **metric label cardinality rất cao**; ID phù hợp hơn ở log/trace được phân quyền.

### Trace không phải thứ tự nghiệp vụ

traceId và timestamp giúp điều tra, nhưng không bảo đảm causal order xuyên nhiều message streams. Một Saga có thể có nhiều traces; correlationId và Saga ID giúp liên kết chúng.

## 36. Kiểm thử dưới lỗi: cần hơn một happy path

### Test A — Duplicate sau commit

1. Consumer nhận E-1 và commit DB.
2. Giả lập crash trước ACK.
3. Broker giao E-1 lần nữa.
4. Xác nhận domain effect chỉ áp một lần và inbox ghi nhận duplicate.

### Test B — Producer retry sau ACK mất

1. Outbox publisher gửi E-1 và broker nhận.
2. Giả lập publisher không lưu checkpoint.
3. Publisher phát lại E-1.
4. Kiểm tra eventId giữ nguyên và consumer không lặp side effect.

### Test C — Out-of-order

1. Gửi OrderCancelled(v3) trước OrderConfirmed(v2).
2. Với snapshot semantics, version guard không cho status lùi.
3. Với delta semantics, consumer phát hiện gap và đợi/rebuild đúng.
4. Kiểm tra log/metrics phản ánh quyết định.

### Test D — Concurrent consumers

1. Hai workers xử lý cùng operationId.
2. Unique constraint/transaction chỉ cho một commit business effect.
3. Worker còn lại trả kết quả đã tồn tại hoặc xử lý duplicate theo contract.

### Test E — Retry topic làm đảo thứ tự

1. Cho v2 lỗi transient và chuyển delayed retry.
2. Cho v3 tới main consumer.
3. Kiểm tra policy strict/pending/version guard.
4. Không được âm thầm mất v2 nếu event v2 mang delta bắt buộc.

### Test F — Partition count thay đổi

1. Tạo topic thử với partition count cũ.
2. Phát nhiều events theo key=orderId.
3. Tăng partition count trong môi trường test.
4. Quan sát key mapping, thứ tự và behavior của consumer.
5. Không áp thay đổi production khi chưa có phương án chuyển đổi.

### Test G — Crash và rebalance

1. Consumer nhận một batch.
2. Một record đang xử lý chậm, record sau hoàn tất.
3. Giả lập rebalance/restart.
4. Xác minh checkpoint không bỏ record chưa hoàn tất.

### Test H — Payment timeout

1. Provider sandbox xác nhận charge nhưng chặn response.
2. Broker giao lại command.
3. Payment Service dùng cùng idempotency reference/tra provider.
4. Kiểm tra không double charge và trạng thái được đối soát.

### Test I — Replay

1. Tạo read model v2 trống.
2. Replay lịch sử events vào projector v2.
3. Xác minh không gửi lại email/charge.
4. Bảo đảm v2 catch up và đối chiếu source trước cutover.

## 37. Bài thực hành Java/Spring và Kafka theo từng bước

Bài tập: tạo một **OrderStatusProjector** nhận events của Ordering. Một Order chỉ có bốn trạng thái PENDING, CONFIRMED, CANCELLED và DELIVERED trong bài học, cùng version tăng.

### Bước 1 — Định nghĩa contract

~~~json
{
  "eventId": "evt-1",
  "eventType": "OrderStatusChanged",
  "aggregateId": "ORD-1001",
  "aggregateVersion": 2,
  "operationId": "confirm-ORD-1001",
  "data": {
    "newStatus": "CONFIRMED"
  }
}
~~~

Viết tài liệu yêu cầu:
- eventId ổn định khi gửi lại;
- aggregateVersion tăng theo commit source;
- key của Kafka là aggregateId;
- consumer phải xử lý duplicate và stale;
- unknown status/version phải được báo theo policy.

### Bước 2 — Tạo bảng

~~~sql
CREATE TABLE order_projection (
    order_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

### Bước 3 — Xử lý transaction

Trong một transaction, insert eventId mới vào processed_events và update order_projection theo version + trạng thái. Nếu event là duplicate, không thực hiện lại tác dụng phụ. Nếu event có gap, nêu rõ lựa chọn đợi hay áp snapshot.

### Bước 4 — Cấu hình producer và consumer

Chọn partition key=orderId và group ID riêng cho projector. Đặt delivery/retry/ack theo Kafka client/framework đang dùng và bảo đảm idempotence configuration tương thích. Không phụ thuộc chỉ vào thứ tự poll nếu handler tự dispatch async.

### Bước 5 — Phát chuỗi lỗi

~~~text
ORD-1001 v1
ORD-1001 v2
ORD-1001 v2 duplicate
ORD-1001 v3
ORD-1001 v2 delayed
ORD-1002 v1
~~~

Kỳ vọng:
- ORD-1001 phản ánh v3 theo state machine.
- Duplicate v2 không tạo tác dụng phụ mới.
- Delayed v2 không làm state quay lại.
- ORD-1002 xử lý độc lập.
- Metrics/logs có duplicate và stale counts.

### Bước 6 — Thử concurrency

Chạy nhiều consumer instances trong cùng group và tạo nhiều keys. Đo throughput, distribution và DB contention. Thử đưa nhiều event vào cùng key để nhìn thấy giới hạn cần serialization.

### Bước 7 — Thử phục hồi

Crash consumer sau DB COMMIT trước offset commit. Khi restart, event bị redelivery nhưng dữ liệu vẫn đúng. Sau đó thử crash trước DB COMMIT; event phải có cơ hội được xử lý lại.

### Bước 8 — Thử replay

Tạo projection v2 riêng, dùng consumer group khác để replay. Không nối listener replay với Payment/email side effects. Đối chiếu kết quả v2 với v1 và nguồn có thẩm quyền.

## 38. Sự khác nhau giữa event stream và business transaction ledger

Đối với tiền và những phép cộng tích lũy, đôi khi cách thiết kế đúng là có **ledger** với transaction IDs và constraints, sau đó phát events từ ledger bằng outbox.

~~~text
Payment ledger:
  transaction TX-1: authorize 500000
  transaction TX-2: capture 500000
  transaction TX-3: refund 100000
~~~

Một read model có thể chiếu ledger thành summary. Nhưng ledger nguồn bảo vệ invariants; consumer không được tạo một giao dịch mới mỗi lần nhận replay event.

Nếu yêu cầu cộng tiền từ delta events, cần giữ mỗi transaction đúng một lần, sequence/version hoặc kiểm tra sự đầy đủ của ledger. **Last-write-wins** không phải mô hình đúng cho mọi tổng tài chính.

## 39. Dữ liệu bảo mật và quyền riêng tư trong event pipeline

Khi event có thể được replay hoặc gửi tới nhiều consumer, thông tin nhạy cảm có thể tồn tại lâu trong broker, DLQ và archive.

Các nguyên tắc:
- Chỉ công bố field thực sự cần cho consumer đã được cấp quyền.
- Bảo vệ producer/consumer identity bằng service credentials, TLS/mTLS khi phù hợp.
- Broker ACL giới hạn topic publish/consume; registry quyền đọc schema không thay thế quyền đọc payload.
- Không gửi payment token/password/raw card information trong event.
- Log chỉ metadata cần thiết; tránh dump nguyên payload PII khi deserialization lỗi.
- DLQ cũng cần retention, encryption và access policy.
- Khi user data bị xóa/ẩn danh theo yêu cầu hợp lệ, cập nhật projections và kế hoạch replay/backup thích hợp.
- Không cho phép một service bất kỳ tự gửi PaymentSucceeded hoặc StockReleased chỉ vì biết event schema.
- Kiểm tra correlation/operation IDs nhưng đừng xem chúng là credential.

Một consumer bị compromise có thể phát lại events hoặc tạo messages giả nếu ACL/identity không kiểm soát. Dedupe và version guard hữu ích nhưng **không thay authentication và authorization của producer**.

## 40. Những anti-pattern cần tránh

### 1. Tin rằng mỗi message chỉ đến một lần

Thành công trong staging không chứng minh không có redelivery khi crash, rebalance, publish timeout hoặc network partition. Thiết kế idempotent ngay từ đầu cho side effects quan trọng.

### 2. Tạo eventId mới mỗi lần retry Outbox

Cùng sự kiện logic có hai IDs khác nhau khiến inbox eventId không phát hiện trùng. EventId phải được xác định và lưu cùng event intent.

### 3. Dedupe bằng payload hash cho mọi loại event

Hai đơn độc lập có payload giống nhau vẫn hợp lệ. Hash có thể dùng phát hiện xung đột cho cùng operation key, nhưng không thay business identity.

### 4. Chỉ kiểm tra eventId, bỏ qua operationId

Hai message khác eventId có thể là cùng một command do client retry. Business operation phải có unique reference riêng.

### 5. Dùng static Map để nhớ processed IDs

Nhiều replicas không chia sẻ Map; restart làm mất. Dùng durable store hoặc constraint ở source authority.

### 6. ACK trước transaction COMMIT

Crash làm mất message chưa có business effect. Xác định commit order đúng và cơ chế redelivery.

### 7. Xử lý offset tuần tự nhưng update DB song song tùy tiện

Bản v2 chậm có thể commit sau v3. Dùng partition/key-aware serialization hoặc version guard.

### 8. Coi timestamp là total order

Đồng hồ nhiều service khác nhau, publish delay và network reorder làm timestamp không đủ để xác lập mọi quan hệ nhân quả.

### 9. Thêm partitions mà không đánh giá key mapping

Một key có thể được chuyển sang partition khác đối với message mới, làm đổi phạm vi ordering quan sát được.

### 10. Dùng retry topic rồi bỏ qua sequence gap

Event v2 lỗi được đưa delayed retry, v3 xử lý thành công. Nếu v2 là delta bắt buộc, dữ liệu bị thiếu.

### 11. Tưởng exactly-once của broker áp cho thanh toán bên ngoài

External provider không nằm trong broker transaction. Cần payment operation ID và reconciliation.

### 12. Dùng một global queue để giữ order không cần thiết

Một message poison có thể chặn mọi Order độc lập. Giữ ordering ở đúng business boundary.

### 13. Bỏ late PaymentSucceeded vô điều kiện

Saga đã hủy nhưng tiền có thể đã thu. Late event cần reconciliation/void/refund theo authority, không chỉ bỏ vì state khác kỳ vọng.

### 14. Replay làm chạy lại external side effects

Dựng lại read model không đồng nghĩa gửi lại email hoặc yêu cầu charge. Tách projector khỏi command handlers.

### 15. Bỏ qua metrics của duplicate và stale events

HTTP API vẫn 200 nhưng side effects sai hoặc projection lùi state. Cần logs, metrics, alerts và reconciliation.

## 41. Checklist thiết kế trước khi đưa vào production

| Hạng mục | Câu hỏi cần quyết định |
| --- | --- |
| Business invariant | Tác động nào tuyệt đối không được lặp hoặc sai thứ tự? |
| Event identity | eventId có giữ nguyên khi publish lại không? |
| Operation identity | Cùng nghiệp vụ được nhận diện bằng khóa nào qua các retry? |
| Aggregate scope | Thứ tự cần theo Order, Account, Customer hay SKU? |
| Partition key | Key có đúng aggregate boundary và distribution không? |
| Broker guarantee | Ordering/delivery trong phạm vi nào và phiên bản cấu hình nào? |
| Producer | Outbox, publish retry, stable IDs, producer idempotence? |
| Outbox ordering | Nhiều publisher có thể đảo version cùng aggregate không? |
| Consumer | Inbox, unique constraints, local transactions, ACK timing? |
| Parallelism | Trong một key có thể có worker xử lý đồng thời không? |
| Versioning | Per-aggregateVersion, snapshot/delta semantics? |
| Gap handling | Khi thiếu v6 mà nhận v7, đợi hay reconstruct? |
| Dedupe retention | Key được giữ bao lâu so với retry/replay/business obligations? |
| External side effect | Payment/email/provider có idempotency hoặc reconciliation không? |
| Retry policy | Retry tại chỗ, delayed retry, quarantine, DLQ? |
| Poison message | Message sai schema có chặn cả partition không? |
| Partition changes | Thêm partition/đổi key ảnh hưởng ordering ra sao? |
| Schema evolution | Producer và consumer cũ/mới có tương thích không? |
| Observability | Duplicate, stale, gap, lag, retry, DLQ, business mismatch? |
| Security | Producer identity, broker ACL, PII, logs, DLQ retention? |
| Replay/rebuild | Có thể dựng lại mà không chạy side effects không? |
| Recovery | Runbook xử lý missing event, timeout, out-of-order? |
| Testing | Có crash before/after commit, rebalance và network faults không? |

## 42. Bài tập ứng dụng

### Bài 1: Chọn ID để chống trùng

Một khách double click “Đặt hàng”. Gateway chuyển hai requests tạo ra hai eventIds khác nhau. Dedupe eventId ở Inventory có đủ không? Hãy thiết kế operationId và unique constraint ở Ordering để chỉ một Order được tạo theo cùng idempotency key.

### Bài 2: Xử lý mất ACK

Consumer đã commit PaymentProjection nhưng crash trước ACK. Khi chạy lại, message đến lần hai. Hãy mô tả transaction inbox + projection và trạng thái nên trả sau duplicate.

### Bài 3: Thiết kế key cho Order lifecycle

Một topic có nhiều Orders. Hãy chọn key để tất cả trạng thái của ORD-1001 cùng partition trong cấu hình ổn định, đồng thời cho ORD-1002 xử lý song song.

### Bài 4: Event v3 đến trước v2

Với hai contract, (A) v3 là snapshot đầy đủ, (B) v3 là delta chỉ chứa số thay đổi, hãy nêu cách xử lý khác nhau và vì sao không thể chỉ dùng sourceVersion > currentVersion cho mọi trường hợp.

### Bài 5: DLQ tạo gap

OrderConfirmed v2 bị lỗi schema và đưa DLQ; OrderCancelled v3 vẫn được xử lý. Nếu projection cần v2 để tính phí hủy, nên sửa thế nào? Nếu v3 là authoritative snapshot, có thể giải quyết khác không?

### Bài 6: Kafka partition expansion

Topic orders.events tăng từ 4 lên 8 partitions và key mapping có thể đổi. Hãy nêu test cần chạy trước triển khai và cơ chế tại consumer giúp chống stale state.

### Bài 7: Hai workers cùng thao tác Inventory

Hai workers nhận cùng ReserveStock(operationId=R-1) đồng thời. SELECT thấy chưa có operation ở cả hai. Thiết kế unique constraint/atomic claim để không giữ hàng hai lần.

### Bài 8: RabbitMQ concurrency

Queue có M1, M2, M3; ba consumers xử lý với thời gian khác nhau. Giải thích vì sao completion order có thể khác delivery order, và cách đảm bảo thứ tự theo entity khi business cần.

### Bài 9: Payment timeout

PSP đã thực hiện charge, response mất. Worker retry với id mới. Phân tích rủi ro, thiết kế provider reference ổn định và cách reconciliation.

### Bài 10: Rebuild projection

Một read model có lỗi và cần replay 30 ngày dữ liệu. Làm sao tránh gửi lại các email trong thời gian rebuild? Nếu broker chỉ còn 7 ngày dữ liệu thì cần nguồn nào khác?

### Bài 11: Event từ hai context

Ordering version=5 và Payments version=3 cùng liên quan ORD-1001. Có thể so sánh 5>3 để bỏ PaymentSucceeded không? Thiết kế sourceVersions độc lập trong read model.

### Bài 12: Kết hợp Inbox và Outbox

Consumer E-1 cập nhật database và tạo event E-2. Nếu service crash trước publish E-2, thiết kế transaction nào bảo đảm E-2 không mất, và vì sao E-2 vẫn có thể được phát lại?

## 43. Câu hỏi tự kiểm tra

1. Duplicate publish khác duplicate delivery như thế nào?
2. EventId khác operationId ở điểm nào?
3. At-least-once cần một consumer có tính chất gì?
4. Exactly-once ở Kafka có nghĩa toàn bộ external payment effect được thực thi đúng một lần không?
5. Outbox giải quyết dual-write gap ở producer thế nào?
6. Inbox và business effect nên được commit ở mối quan hệ transaction nào?
7. Vì sao một event được ACK trước DB COMMIT có thể bị mất business effect?
8. Một Kafka partition có bảo đảm thứ tự áp DB khi consumer dispatch async không?
9. AggregateVersion khác broker offset như thế nào?
10. Tại sao key=eventId thường không phù hợp để giữ thứ tự events của một Order?
11. Việc tăng partition count có thể thay key-to-partition mapping không?
12. Vì sao không có total order giữa events thuộc các topics khác nhau?
13. Khi v3 đến trước v2, snapshot và delta cần cách xử lý giống nhau không?
14. Retry topic có thể làm đảo thứ tự effect theo entity như thế nào?
15. Khi xử lý song song, checkpoint nên theo offset lớn nhất hoàn tất hay prefix liên tục đã hoàn tất?
16. RabbitMQ có bảo đảm completion order khi nhiều consumers xử lý cùng queue không?
17. Vì sao một thao tác ChargePayment phải có provider idempotency reference?
18. Có thể bỏ late PaymentAuthorized khi Saga đã COMPENSATING không?
19. Replay read model có được phép phát lại email hoặc charge không?
20. Khi một hot key giới hạn throughput, nên xem lại loại business invariant nào?
21. Bảo vệ chống trùng ở business source khác gì metrics duplicate detected?
22. Schema Registry có thay thế event identity, ordering và idempotency không?
23. Nếu một consumer đã thấy v7 nhưng thiếu v6, có những lựa chọn recovery nào?
24. Vì sao log timestamp không phải cơ chế duy nhất xác định business ordering?

## 44. Tổng kết

Để truyền sự kiện tin cậy, hệ thống phải **chịu được duplicate** và **bảo vệ thứ tự trong đúng phạm vi cần thiết**. Đây là hai bài toán có liên quan nhưng không đồng nhất.

- **Duplicate:** dùng eventId ổn định cho redelivery, operationId cho yêu cầu nghiệp vụ, Outbox ở producer, Inbox/unique constraint/transaction ở consumer và idempotency tại external provider khi có side effect.
- **Ordering:** chọn aggregate boundary, key/partition phù hợp; hiểu giới hạn broker log order; kết hợp aggregateVersion, state machine, gap handling và concurrency control.
- **Recovery:** ACK sau durable update theo mô hình tiêu thụ, retry có kiểm soát, xử lý DLQ/quarantine, reconciliation khi timeout, và replay không làm lặp side effects.
- **Observability:** đo duplicate, stale events, sequence gaps, consumer lag, outbox backlog và các sai lệch business, chứ không chỉ nhìn số message đã đọc.

Thay vì đặt mục tiêu “không bao giờ có message trùng và mọi message trên thế giới đều đúng thứ tự”, hãy thiết kế để **dù message được giao lại, đến muộn, sai thứ tự hoặc thiếu tạm thời, mỗi bất biến nghiệp vụ quan trọng vẫn được bảo vệ và hệ thống có đường khôi phục rõ ràng**.
