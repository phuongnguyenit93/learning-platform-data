# Cho rằng broker bảo đảm mọi tác dụng phụ chỉ xảy ra một lần

Một message broker có thể cung cấp những bảo đảm giao nhận và xử lý rất hữu ích, nhưng điều đó **không đồng nghĩa mọi tác dụng phụ nghiệp vụ chỉ xảy ra đúng một lần**. Đây là một ngộ nhận nguy hiểm trong microservices: nhóm bật producer idempotence, Kafka transactions, manual ACK hoặc một tùy chọn “exactly once”, rồi cho rằng payment, invoice, email, database update và lời gọi API ngoài sẽ không bao giờ bị thực hiện trùng.

Thực tế, một workflow có thể đi qua nhiều ranh giới độc lập: database của producer, broker, database của consumer, payment provider, email service và các hệ thống downstream. Không có một transaction broker đơn lẻ nào tự động bao trùm tất cả các hệ thống đó. Process có thể crash giữa hai bước; network timeout có thể xảy ra sau khi phía nhận đã commit; broker có thể giao lại message; client có thể retry một request mà kết quả trước đó chưa rõ.

Cần phân biệt rõ:

- **Delivery:** broker giao message cho consumer bao nhiêu lần?
- **Processing:** consumer thực thi handler bao nhiêu lần?
- **Commit:** offset hoặc ACK được xác nhận ở thời điểm nào?
- **State transition:** database ghi nhận thay đổi bao nhiêu lần?
- **External side effect:** payment, email, webhook hoặc API đối tác được thực hiện bao nhiêu lần?
- **Business outcome:** nghiệp vụ cuối cùng có đúng một kết quả hợp lệ hay không?

Một hệ thống đáng tin thường kết hợp **at-least-once delivery, idempotent consumer, transaction boundary rõ, unique constraints, idempotency key theo nghiệp vụ và reconciliation**. Mục tiêu là một business effect duy nhất dù message có thể được giao hoặc handler được chạy nhiều lần.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao broker delivery guarantee không tự bảo đảm exactly-once business effect.
2. Phân biệt producer idempotence, broker transaction, consumer offset/ACK, database transaction và external side effect.
3. Phân tích các failure windows khi process crash hoặc network timeout giữa các bước.
4. Thiết kế idempotent consumer với inbox/processed-message table và unique constraint.
5. Chọn idempotency key theo ý nghĩa nghiệp vụ thay vì chỉ dựa vào message ID.
6. Dùng transactional outbox để không mất event giữa database commit và broker publish.
7. Xử lý external provider bằng idempotency key, query trạng thái và reconciliation.
8. Phân biệt duplicate delivery với duplicate business intent.
9. Xử lý retry, DLQ, replay, ordering và concurrency mà không tạo side effect trùng.
10. Xây dựng test cho crash-after-commit, timeout-unknown, redelivery và concurrent duplicate.
11. Định nghĩa metric và runbook để phát hiện duplicate, pending state và sai lệch.
12. Chọn đúng mức bảo đảm cần thiết cho từng use case, thay vì hứa hẹn exactly-once ở mọi tầng.

## 2. Vì sao ngộ nhận này xuất hiện?

Trong tài liệu broker có thể gặp những cụm từ như idempotent producer, transactional producer, exactly-once processing, manual acknowledgement hoặc deduplication. Những cơ chế này giải quyết **một phạm vi cụ thể**. Khi rút gọn thành câu “broker bảo đảm message chỉ xử lý một lần”, phạm vi bảo đảm đã bị mở rộng quá mức.

Một workflow điển hình:

~~~text
Order Service
    |
    | 1. Commit order
    v
Order Database
    |
    | 2. Publish OrderPlaced
    v
Message Broker
    |
    | 3. Deliver to consumer
    v
Billing Consumer
    |
    | 4. Create invoice
    v
Billing Database
    |
    | 5. Call payment/email/provider
    v
External System
~~~

Mỗi mũi tên là một ranh giới lỗi riêng. Broker có thể quản lý việc lưu message và giao lại, nhưng không biết database consumer đã commit hay external provider đã thực hiện payment nếu consumer mất kết nối đúng lúc.

Một log ghi “message received” chỉ chứng minh handler đã bắt đầu. Một ACK thành công chỉ chứng minh broker nhận tín hiệu ACK theo protocol. Một database commit chỉ chứng minh transaction trong database đó đã hoàn tất. Không sự kiện đơn lẻ nào chứng minh toàn bộ workflow chỉ tạo ra một side effect.

## 3. Phân biệt các tầng bảo đảm

| Tầng | Cơ chế thường gặp | Phạm vi bảo đảm | Điều không tự bảo đảm |
|---|---|---|---|
| Producer → broker | Producer idempotence, sequence numbers, confirms | Giảm duplicate do producer retry trong phạm vi broker hỗ trợ | DB và broker commit nguyên tử |
| Broker transaction | Kafka transaction | Atomic read/process/write trong phạm vi Kafka và cấu hình phù hợp | Transaction với PostgreSQL hoặc HTTP provider |
| Broker → consumer | ACK, offset commit, redelivery | Xác nhận message đã được consumer xử lý theo protocol | Handler chỉ chạy một lần |
| Consumer database | DB transaction, unique constraint | State change có thể được commit một lần theo key | Email/payment ngoài DB không trùng |
| Consumer logic | Idempotency key, inbox table | Duplicate command/event không lặp business transition | Mọi external system đều hỗ trợ dedup |
| External provider | Provider idempotency key | Provider có thể deduplicate request theo contract của họ | Mọi nhà cung cấp hoặc mọi thời hạn đều hỗ trợ |
| Toàn workflow | Saga, reconciliation, business invariants | Đưa hệ thống về kết quả hợp lệ qua nhiều bước | Một transaction phân tán nguyên tử tự động |

### 3.1. Exactly-once phải luôn có phạm vi

Khi nghe “exactly once”, hãy hỏi:

1. Exactly once đối với message được append vào broker?
2. Exactly once đối với output record của một Kafka transaction?
3. Exactly once đối với handler invocation?
4. Exactly once đối với row trong một database?
5. Exactly once đối với request gửi tới payment provider?
6. Exactly once đối với kết quả nghiệp vụ cuối cùng?

Nếu câu trả lời không xác định được hệ thống, transaction boundary, key và failure model, tuyên bố exactly-once chưa đủ ý nghĩa để làm yêu cầu kiến trúc.

## 4. At-most-once, at-least-once và exactly-once

### 4.1. At-most-once

Consumer xác nhận/commit trước hoặc theo cách không retry sau khi lỗi. Message có thể bị mất nếu process chết trước khi business side effect hoàn tất.

~~~text
Receive
  |
Commit/ACK
  |
Process
  |
Crash before DB commit
  |
Message may not be delivered again
~~~

Cách này có thể phù hợp với một số telemetry có thể bỏ qua, nhưng thường không phù hợp với event nghiệp vụ quan trọng.

### 4.2. At-least-once

Consumer chỉ ACK/commit sau khi xử lý. Nếu process crash sau business commit nhưng trước ACK/offset commit, broker có thể giao message lại.

~~~text
Receive
  |
DB transaction commits
  |
Process crashes before ACK
  |
Broker redelivers
  |
Handler runs again
~~~

Đây là mô hình phổ biến và thực dụng. Nó ưu tiên không mất message nhưng đòi hỏi consumer xử lý duplicate an toàn.

### 4.3. Exactly-once processing trong phạm vi broker

Một số broker có transaction hoặc idempotence để giới hạn duplicate trong một workflow cụ thể. Kafka hỗ trợ idempotent producer và transaction để phối hợp consume offsets với produce records trong Kafka. Điều này hữu ích cho stream processing khi input và output đều nằm trong phạm vi Kafka transaction.

Tuy nhiên, nếu consumer ghi PostgreSQL rồi commit Kafka offset, hai thao tác vẫn thuộc hai transaction manager khác nhau trừ khi có một cơ chế tích hợp cụ thể đã được chứng minh. Nếu consumer gọi HTTP provider, broker transaction không thể tự rollback side effect phía provider.

**Không được diễn giải exactly-once trong Kafka thành exactly-once cho payment, email, DB và mọi downstream.**

## 5. Failure window: commit database rồi crash trước ACK

Đây là tình huống cơ bản:

~~~text
T0  Consumer nhận event E
T1  Consumer bắt đầu DB transaction
T2  Consumer tạo invoice
T3  DB COMMIT thành công
T4  Process crash
T5  Offset chưa commit / ACK chưa được broker nhận
T6  Broker giao lại E
T7  Consumer chạy lại
~~~

Nếu handler không có deduplication, T7 có thể tạo invoice thứ hai.

Cần nhớ: việc consumer không nhận được response ACK không chứng minh broker chưa nhận ACK; tương tự, consumer timeout khi gọi DB không chứng minh transaction chưa commit. Hệ thống phải xử lý kết quả không chắc chắn bằng key và truy vấn trạng thái.

### 5.1. Failure window ngược lại: ACK trước DB commit

~~~text
T0  Consumer nhận event E
T1  ACK/offset commit thành công
T2  Consumer bắt đầu DB transaction
T3  Process crash trước DB COMMIT
T4  Broker không giao lại E
T5  Business effect bị mất
~~~

Vì vậy, với side effect trong database, thường phải commit DB trước rồi mới ACK/commit offset. Điều này tạo duplicate window, được xử lý bằng idempotency.

### 5.2. ACK timeout không có nghĩa business thất bại

Nếu client gửi ACK rồi mất network trước khi nhận response, consumer có thể không biết broker đã nhận hay chưa. Message có thể không được giao lại hoặc có thể được giao lại tùy trạng thái thực tế. Hệ thống không nên suy luận từ một timeout đơn lẻ; cần idempotent handling và broker observability.

## 6. Failure window khi gọi external provider

Giả sử Billing Consumer gọi cổng thanh toán:

~~~text
Consumer
   |
   | POST /charges
   v
Payment Provider
   |
   | Charge is committed
   v
Provider Database
   |
   | Response is lost
   v
Consumer times out
~~~

Consumer thấy timeout nhưng provider đã tạo charge. Nếu consumer gửi lại một request mới với key khác, khách hàng có thể bị charge hai lần.

Đây là **unknown outcome**: phía gọi không biết request đã được thực hiện hay chưa. Retry vô điều kiện có thể tạo side effect trùng; bỏ qua cũng có thể làm giao dịch bị treo.

Các biện pháp:

- Dùng idempotency key ổn định cho cùng một ý định payment.
- Lưu provider reference và trạng thái request.
- Khi timeout, truy vấn provider theo idempotency key/reference nếu API hỗ trợ.
- Không tạo key mới cho lần retry cùng một business operation.
- Phân biệt timeout, declined, accepted/pending và confirmed.
- Có reconciliation job đối chiếu trạng thái nội bộ với provider.
- Nếu provider không hỗ trợ idempotency hoặc lookup, cần quy trình xử lý thủ công/đối soát có kiểm soát; không tuyên bố exactly-once.

## 7. Producer idempotence không phải consumer idempotency

Producer idempotence giúp broker nhận diện một số lần retry gửi cùng record từ producer session/sequence theo semantics của broker. Nó có thể tránh duplicate record do producer retry trong các trường hợp được hỗ trợ.

Nó không thể ngăn:

- Hai HTTP requests độc lập cùng tạo một order.
- Hai instance ứng dụng tạo hai event IDs cho cùng một business intent.
- Outbox relay publish lại sau khi crash nếu không có dedup ở consumer.
- Consumer xử lý cùng message nhiều lần.
- External API được gọi lại sau timeout.
- Hai producer khác nhau phát cùng business fact mà không có common key.

Consumer idempotency là trách nhiệm riêng. Một consumer cần nhận diện cùng một event hoặc cùng một business operation và đảm bảo xử lý lặp lại không thay đổi kết quả lần thứ hai.

## 8. Hai loại duplicate cần phân biệt

### 8.1. Duplicate delivery

Cùng một message logic được giao nhiều lần:

~~~text
eventId = E-100
delivery attempt 1
delivery attempt 2
delivery attempt 3
~~~

Dùng event ID để deduplicate.

### 8.2. Duplicate business intent

Hai message khác ID nhưng thực chất cùng một yêu cầu nghiệp vụ:

~~~text
eventId = E-100, commandId = C-55, orderId = O-9
eventId = E-101, commandId = C-55, orderId = O-9
~~~

Nếu chỉ deduplicate theo event ID, cả hai message có thể được xử lý. Cần business idempotency key như command ID, payment attempt ID, reservation request ID hoặc invoice business reference tùy use case.

### 8.3. Không dùng một key cho mọi thứ

- **eventId:** định danh event logic.
- **commandId:** định danh ý định/command.
- **paymentOperationId:** định danh thao tác payment.
- **invoiceNumber** hoặc unique order reference: định danh invoice theo nghiệp vụ.
- **notificationDeliveryKey:** định danh lần gửi notification cần deduplicate.
- **aggregateVersion:** thứ tự thay đổi của entity.

Một order có thể có nhiều lần payment/refund hợp lệ. Dùng orderId làm key cho mọi payment effect sẽ chặn nhầm các giao dịch hợp lệ.

## 9. Thiết kế idempotent consumer với inbox table

Một mẫu phổ biến là lưu event đã xử lý trong cùng database với business state.

~~~sql
CREATE TABLE processed_messages (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer thực hiện:

~~~text
BEGIN DB TRANSACTION

1. INSERT (consumer_name, event_id)
   ON CONFLICT DO NOTHING

2. Nếu không insert được:
      Đây là event đã xử lý.
      Không lặp side effect.
      COMMIT

3. Nếu insert được:
      Validate business transition.
      Cập nhật invoice/order/payment state.
      Ghi outbox event tiếp theo nếu cần.

COMMIT DB TRANSACTION

4. ACK / commit offset
~~~

Điều kiện quan trọng: **processed marker và business side effect phải nằm trong cùng một transaction** nếu chúng ở cùng database.

Nếu ghi marker trước rồi crash trước khi update invoice, lần giao lại sẽ bị coi là duplicate dù invoice chưa được tạo. Nếu update invoice trước nhưng marker nằm trong transaction khác, crash có thể tạo invoice trùng.

### 9.1. SQL với conflict handling

~~~sql
BEGIN;

INSERT INTO processed_messages (
    consumer_name, event_id
)
VALUES (
    'billing-service', :event_id
)
ON CONFLICT DO NOTHING;

-- Application kiểm tra số row vừa insert.
-- Chỉ khi có row mới thì tiếp tục domain update.

INSERT INTO invoices (
    invoice_id, order_id, status
)
VALUES (
    :invoice_id, :order_id, 'CREATED'
)
ON CONFLICT (order_id) DO NOTHING;

COMMIT;
~~~

Đây là ví dụ giản lược. Không nên chỉ dựa vào ON CONFLICT DO NOTHING rồi coi nghiệp vụ đã đúng. Cần kiểm tra outcome của insert/update, unique constraint phù hợp, version và trạng thái hiện tại. Nếu invoice đã tồn tại nhưng có dữ liệu khác, cần xử lý conflict theo domain thay vì âm thầm bỏ qua.

### 9.2. Consumer name là một phần của dedup scope

Cùng một event có thể được hai consumer khác nhau xử lý hợp lệ. Vì vậy primary key thường bao gồm consumer name/group và event ID. Không dùng một bảng dedup toàn cục khiến consumer Billing chặn consumer Analytics.

Consumer name cần ổn định qua deploy; nếu đổi tên group tùy tiện, hệ thống có thể xem toàn bộ lịch sử là mới và replay side effects. Việc tạo consumer group mới phải có kế hoạch replay/dedup riêng.

## 10. Idempotency key theo business operation

Một thao tác được gọi là idempotent khi thực hiện lại cùng một ý định không làm thay đổi kết quả nghiệp vụ thêm lần nữa.

Ví dụ API payment:

~~~http
POST /payments/authorize
Idempotency-Key: payment-attempt-2026-7812-1
Content-Type: application/json
~~~

Nếu client retry cùng request vì timeout, provider/application nhận cùng key và trả lại kết quả đã lưu hoặc trạng thái tương ứng thay vì tạo authorization mới.

Key phải:

- Được tạo một lần cho business operation và lưu bền vững.
- Ổn định qua retries, process restart và broker redelivery.
- Có scope rõ: tenant, endpoint, operation type hoặc merchant account.
- Không chứa secret/PII trực tiếp.
- Có retention đủ dài hơn thời gian retry/replay hợp lệ.
- Được ràng buộc với request fingerprint hoặc payload hash phù hợp.
- Có semantics khi cùng key nhưng payload khác nhau: reject conflict, không âm thầm dùng kết quả cũ.

Không sinh UUID mới mỗi lần retry. Nếu key mới, hệ thống không còn nhận ra hai request thuộc cùng ý định.

### 10.1. Lưu kết quả idempotency

Một bảng khái niệm:

~~~sql
CREATE TABLE idempotency_records (
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    response_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, idempotency_key)
);
~~~

Các trạng thái có thể gồm IN_PROGRESS, SUCCEEDED, FAILED_FINAL, UNKNOWN hoặc domain-specific states. Khi key đang được xử lý, request song song phải chờ, nhận trạng thái pending hoặc bị từ chối retry theo contract. Không để hai worker cùng thực hiện side effect chỉ vì cả hai đọc thấy “chưa có record” trước khi insert; unique constraint/atomic claim phải giải quyết race.

## 11. Concurrency: hai consumer cùng nhận cùng business intent

Ngay cả khi broker chỉ giao một message một lần trong điều kiện bình thường, duplicate có thể xuất hiện qua hai luồng khác nhau, hai topics hoặc hai command requests.

~~~text
Worker A                 Worker B
   |                         |
   | check key absent        | check key absent
   |                         |
   | create payment          | create payment
   |                         |
   v                         v
Two side effects
~~~

Một thao tác read-then-write không đủ để chống race. Cần atomic primitive:

- Unique constraint ở database.
- Insert-on-conflict/compare-and-set.
- Optimistic locking với version.
- Row-level lock khi phù hợp.
- Atomic idempotency claim.
- Provider-side idempotency key.

Không chỉ dùng synchronized trong Java process vì nhiều replicas có bộ nhớ riêng. Distributed lock có thể giúp điều phối nhưng vẫn cần fencing/version/unique constraint để chống worker cũ tiếp tục ghi sau khi lease hết hạn.

## 12. Transactional outbox: bảo đảm phát event gắn với business commit

Producer cũng có failure window:

~~~text
UPDATE order; COMMIT
       |
       | crash
       v
PUBLISH event never happens
~~~

Transactional outbox ghi business state và event intent trong cùng transaction:

~~~text
BEGIN
  UPDATE orders ...
  INSERT INTO outbox(event_id, payload, ...)
COMMIT
       |
       v
Outbox relay / CDC
       |
       v
Broker
~~~

Khi transaction commit, cả business change và outbox row cùng tồn tại. Relay có thể gửi lại sau lỗi; do đó consumer vẫn phải idempotent.

### 12.1. Outbox không tự tạo exactly-once publish

Một relay có thể:

1. Publish event thành công.
2. Crash trước khi đánh dấu row đã publish.
3. Restart và publish lại event.

Đây là behavior at-least-once. Đừng cố tránh mọi duplicate bằng cách đánh dấu published trước khi gửi; làm vậy tạo nguy cơ mất event nếu crash sau mark nhưng trước publish.

Thiết kế đúng là publish có thể lặp, consumer deduplicate theo eventId và relay theo dõi backlog.

### 12.2. CDC và polling relay

Polling relay cần atomic claiming/locking để nhiều instances không cùng xử lý sai. CDC relay cần quản lý connector offsets, schema, tombstones, snapshot và recovery. Dù chọn cách nào, cần có metric outbox age, pending count, publish failures và reconciliation giữa outbox với broker/sink.

## 13. Kafka transactions: bảo đảm trong phạm vi Kafka

Kafka transaction có thể phối hợp đọc message, ghi output records và commit consumed offsets trong cùng transaction Kafka. Một stream processing task có thể:

~~~text
Read input topic
    |
Process record
    |
Produce output topic
    |
Commit output + input offsets atomically
~~~

Consumer đọc output ở isolation level phù hợp để không thấy record chưa commit. Cấu hình producer idempotence/transactional ID và consumer isolation phải đúng theo broker/client version.

Những điều cần hiểu:

- Transactional ID cần ổn định và duy nhất theo producer instance semantics.
- Transaction timeout và fencing ảnh hưởng producer cũ.
- Offset commit phải tham gia transaction theo cách framework hỗ trợ.
- External database write không tự nằm trong Kafka transaction.
- HTTP provider call không rollback khi Kafka transaction abort.
- Consumer side effect ngoài Kafka vẫn cần idempotency/reconciliation.

### 13.1. Spring Kafka và transaction

Spring Kafka có thể cấu hình transactional producer/listener container. API và cấu hình phụ thuộc version. Cần đọc documentation đúng version đang dùng, xác minh transaction manager, offset handling và listener error semantics bằng integration tests.

Không thêm một property transaction rồi tuyên bố toàn bộ workflow exactly-once. Hãy viết rõ: “Kafka input offsets và Kafka output records được commit atomically trong luồng này; DB/external effects được bảo vệ bằng inbox/outbox/idempotency.”

## 14. RabbitMQ ACK, confirms và redelivery

RabbitMQ publisher confirms và consumer acknowledgements giải quyết hai phía khác nhau:

- **Publisher confirm:** broker xác nhận publish theo semantics và durability configuration.
- **Consumer ACK:** consumer xác nhận message đã xử lý theo protocol.
- **Redelivery:** message có thể được giao lại nếu channel/connection đóng trước ACK hoặc requeue/retry policy kích hoạt.
- **Persistent message/quorum queue:** tăng durability theo topology, nhưng không tạo transaction với database consumer.

Một consumer có thể commit DB rồi mất kết nối trước ACK. Broker giao lại message. Inbox/idempotency vẫn cần thiết.

Publisher confirm không chứng minh consumer đã xử lý; consumer ACK không chứng minh external email/payment chỉ xảy ra một lần.

## 15. External side effect: payment provider

Payment là ví dụ có hậu quả lớn nếu duplicate.

### 15.1. Workflow phù hợp

~~~text
Receive AuthorizePayment
        |
        v
Claim paymentOperationId
        |
        v
Persist status = REQUESTED
        |
        v
Call provider with same idempotency key
        |
        +-- Confirmed --> persist AUTHORIZED
        |
        +-- Declined --> persist DECLINED
        |
        +-- Timeout --> persist UNKNOWN
                           |
                           v
                 Query provider/reconcile
~~~

Không coi timeout là decline. Provider có thể đã authorize nhưng response bị mất.

### 15.2. Provider idempotency contract

Trước khi dựa vào idempotency của provider, xác minh:

- Key có scope theo merchant/account hay toàn hệ thống?
- Thời hạn lưu key là bao lâu?
- Cùng key nhưng payload khác trả lỗi hay trả kết quả cũ?
- Request đang xử lý trả trạng thái nào?
- Có API query theo key/reference không?
- Retry sau timeout có an toàn không?
- Refund/capture có key riêng không?
- Sandbox có mô phỏng duplicate/timeout đúng không?

Nếu provider chỉ giữ key trong 24 giờ, retry/replay sau 3 ngày có thể không còn được deduplicated. Ứng dụng cần local operation record và reconciliation; không phụ thuộc duy nhất vào provider cache.

## 16. External side effect: email, SMS và webhook

Email/SMS thường khó hoàn tác. Một consumer gửi email rồi crash trước khi ACK có thể gửi lại.

Các lựa chọn:

- Notification provider hỗ trợ idempotency key hoặc client reference.
- Lưu delivery operation với unique key theo notification intent.
- Tạo outbox cho notification request.
- Query provider status nếu API có hỗ trợ.
- Dùng delivery state machine: REQUESTED, ACCEPTED, SENT, DELIVERED, FAILED, UNKNOWN.
- Với provider không hỗ trợ dedup, xác định chấp nhận duplicate hiếm gặp hay cần workflow reconciliation/manual review.

Không dùng eventId duy nhất cho nhiều notification khác nhau nếu cùng event tạo nhiều loại email hợp lệ. Key nên gồm notification purpose/version và recipient reference được bảo vệ.

Webhook outbound cũng cần signing, retry/backoff và stable delivery ID. Receiver nên có idempotent endpoint vì webhook thường được gửi lại khi sender không nhận được 2xx.

## 17. Database unique constraints là lớp bảo vệ cuối

Application code có thể có race hoặc bug. Database constraint giúp bảo vệ invariant tại nơi state được commit.

Ví dụ:

~~~sql
CREATE TABLE invoices (
    invoice_id UUID PRIMARY KEY,
    order_id UUID NOT NULL UNIQUE,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Nếu nghiệp vụ quy định một invoice chính cho mỗi order, unique constraint trên order_id ngăn hai transaction tạo hai invoice dù hai worker chạy đồng thời.

Nhưng phải xác định invariant đúng. Một order có thể có nhiều invoice adjustment hoặc refund document; khi đó unique constraint cần dựa trên loại và operation reference phù hợp.

### 17.1. Không chỉ dựa vào kiểm tra trước

Mẫu không an toàn:

~~~text
SELECT invoice WHERE order_id = ?
if not found:
    INSERT invoice
~~~

Hai transaction có thể cùng SELECT và không thấy invoice, rồi cùng INSERT. Dùng unique constraint và xử lý conflict. Lock/serializable isolation có thể phù hợp một số case nhưng cần hiểu throughput và deadlock.

## 18. Idempotent state transition

Ngoài dedup event, domain method cũng có thể được thiết kế idempotent:

~~~java
public PaymentResult authorize(PaymentCommand command) {
    PaymentOperation operation =
        repository.findByBusinessKey(command.operationId())
            .orElseGet(() -> repository.createPending(command));

    if (operation.isAuthorized()) {
        return PaymentResult.alreadyAuthorized(operation.reference());
    }

    if (operation.isFinalFailure()) {
        return PaymentResult.finalFailure(operation.failureCode());
    }

    return providerGateway.authorize(
        operation.amount(),
        operation.currency(),
        operation.idempotencyKey()
    );
}
~~~

Đây là pseudocode. Trong thực tế, find-or-create phải atomic bằng unique constraint/insert-on-conflict; nhiều replicas có thể chạy đồng thời. Không giữ transaction DB mở trong khi gọi provider lâu. Cần lưu state trước/sau provider call và xử lý trạng thái UNKNOWN.

Một transition idempotent không có nghĩa bỏ qua mọi lần gọi lặp. Nó trả lại kết quả đã xác định hoặc tiếp tục cùng operation theo policy, không tạo operation mới.

## 19. Retry không được tạo business intent mới

Retry transport và retry nghiệp vụ khác nhau:

- **Transport retry:** gửi lại cùng event/message do chưa biết broker đã nhận chưa.
- **Consumer retry:** xử lý lại cùng event do lỗi tạm thời.
- **Business retry:** tạo một operation mới theo quyết định nghiệp vụ, ví dụ thử payment lần hai sau khi người dùng đổi phương thức.
- **Manual replay:** operator yêu cầu xử lý lại message sau khi sửa lỗi.

Mỗi loại cần ID và audit riêng. Transport retry thường giữ eventId và idempotency key. Business retry có thể tạo operation ID mới nhưng phải liên kết với operation trước và tuân theo state machine.

Không tạo UUID mới mỗi lần consumer retry; như vậy duplicate detection mất tác dụng.

### 19.1. Retry với backoff

~~~text
attempt 1 -> wait 1s
attempt 2 -> wait 2s
attempt 3 -> wait 4s
attempt 4 -> wait 8s
max attempts / max elapsed reached
        |
        v
DLQ or reconciliation queue
~~~

Lịch là ví dụ, cần thêm jitter, timeout và giới hạn. Với provider rate limit, tuân thủ Retry-After. Với lỗi permanent hoặc invalid state, không retry liên tục.

## 20. DLQ replay và dedup retention

Một lỗi phổ biến: DLQ giữ message lâu hơn inbox dedup record. Khi operator replay message, processed marker đã bị xóa theo TTL; consumer xử lý lại side effect.

Cần phối hợp retention:

- Inbox/dedup retention phải bao phủ broker retention, retry window, DLQ retention và replay window.
- External provider idempotency retention cần được xét riêng.
- Business unique constraints có thể giữ lâu hơn event dedup.
- Nếu phải replay lịch sử cũ, cần mode replay không phát side effects hoặc rebuild projection ở namespace riêng.
- Manual replay phải ghi actor, reason, message IDs, range, batch size và outcome.

Không xóa processed marker chỉ để tiết kiệm storage nếu vẫn có thể replay message cũ. Có thể archive/partition inbox table hoặc giữ business operation ledger bền vững.

## 21. Ordering không thay thế idempotency

Một partition hoặc queue có thể giữ một số ordering guarantees, nhưng message vẫn có thể được redeliver. Ordering chỉ nói thứ tự tương đối; nó không ngăn duplicate.

Ví dụ:

~~~text
Order version 17: OrderPlaced
Order version 18: PaymentAuthorized
Order version 19: OrderConfirmed
~~~

Consumer nên kiểm tra aggregate version:

- Version tiếp theo đúng: xử lý.
- Version đã áp dụng: duplicate/old event, không lặp side effect.
- Version nhảy có gap: hold/reconcile, không tự bỏ qua.
- Event không thuộc sequence này: áp dụng semantics riêng.

Nếu event version 18 bị giao hai lần, ordering vẫn có thể đúng nhưng handler vẫn chạy hai lần. Inbox/idempotency vẫn cần thiết.

## 22. Saga: một business workflow không phải một transaction

Một order có thể trải qua nhiều service:

~~~text
OrderCreated
   |
   v
ReserveInventory
   |
   +-- InventoryReserved
   |        |
   |        v
   |   AuthorizePayment
   |        |
   |        +-- PaymentAuthorized
   |        |       |
   |        |       v
   |        |   ConfirmOrder
   |        |
   |        +-- PaymentDeclined
   |                |
   |                v
   |          ReleaseInventory
   |
   +-- InventoryRejected
            |
            v
       CancelOrder
~~~

Mỗi bước có local transaction và có thể được retry. Saga coordinator hoặc choreography phải giữ workflow state và command IDs ổn định.

Compensation là một business action mới, không phải rollback vật lý:

- Release inventory reservation.
- Void payment authorization.
- Refund captured payment.
- Cancel shipment.
- Issue correction event.

Compensation cũng có thể thất bại hoặc bị giao lại, nên bản thân nó phải idempotent. Saga cần timeout, retry, reconciliation và trạng thái UNKNOWN.

## 23. Outbox + inbox: mẫu phối hợp phổ biến

Một service nhận event, cập nhật DB và phát event mới:

~~~text
Broker input
    |
    v
Consumer
    |
    v
BEGIN DB TRANSACTION
    |
    +--> INSERT inbox(event_id) if new
    |
    +--> UPDATE business state
    |
    +--> INSERT outbox(next_event)
    |
COMMIT
    |
    v
ACK input
    |
    v
Outbox relay publishes next event
~~~

Mẫu này tạo một ranh giới transaction rõ bên trong service:

- Inbox ngăn event được xử lý nghiệp vụ hai lần.
- Business state update và inbox marker commit cùng nhau.
- Outbox đảm bảo event tiếp theo được lưu cùng business state.
- Broker delivery có thể lặp, relay publish có thể lặp.
- Downstream consumers tiếp tục dùng inbox/idempotency.

Đây không phải exactly-once toàn hệ thống. Nó là chuỗi các local transactions có thể phục hồi và xử lý lặp an toàn.

## 24. Ví dụ Spring: inbox và transaction

Entity/repository có thể được thiết kế theo hướng:

~~~java
@Entity
@Table(
    name = "processed_messages",
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"consumer_name", "event_id"}
    )
)
public class ProcessedMessage {
    @Id
    private UUID id;

    @Column(name = "consumer_name", nullable = false)
    private String consumerName;

    @Column(name = "event_id", nullable = false)
    private UUID eventId;

    protected ProcessedMessage() {}

    public ProcessedMessage(String consumerName, UUID eventId) {
        this.id = UUID.randomUUID();
        this.consumerName = consumerName;
        this.eventId = eventId;
    }
}
~~~

Service xử lý:

~~~java
@Service
public class BillingEventHandler {
    private final ProcessedMessageRepository inbox;
    private final InvoiceRepository invoices;
    private final OutboxRepository outbox;

    @Transactional
    public void handle(OrderPlacedEvent event) {
        if (inbox.existsByConsumerNameAndEventId(
                "billing-service", event.eventId())) {
            return;
        }

        inbox.save(new ProcessedMessage(
            "billing-service", event.eventId()
        ));

        invoices.createIfAbsent(
            event.orderId(),
            event.totalMinorUnits(),
            event.currency()
        );

        outbox.append(
            InvoiceRequestedEvent.from(event)
        );
    }
}
~~~

Đây là skeleton minh họa. Kiểm tra exists rồi save riêng có race condition nếu hai replicas cùng xử lý event. Cần dùng atomic insert với unique constraint và bắt conflict đúng cách; tùy JPA/provider, transaction có thể bị rollback khi unique violation. Có thể dùng native INSERT ON CONFLICT DO NOTHING hoặc repository method chuyên biệt. Side effect và inbox marker phải cùng transaction.

### 24.1. Consumer ACK sau khi transaction hoàn tất

Với listener container, handler method nên trả về sau khi transaction service commit thành công; cấu hình ACK/offset phải bảo đảm commit theo kết quả listener. Nếu dùng async method hoặc gọi thread khác, listener có thể ACK trước khi future hoàn tất. Không fire-and-forget side effect rồi để container tự commit.

## 25. Java: unique claim atomic bằng SQL

Một ví dụ PostgreSQL để claim event:

~~~sql
INSERT INTO processed_messages (
    consumer_name,
    event_id,
    processed_at
)
VALUES (
    :consumer_name,
    :event_id,
    now()
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Ứng dụng kiểm tra row count:

- 1 row inserted: consumer sở hữu lần xử lý mới trong transaction hiện tại.
- 0 rows inserted: event đã được claim/processed theo semantics của bảng.
- DB error: transaction thất bại; không ACK như thể đã xử lý.

Nếu transaction rollback, marker mới cũng rollback. Nếu commit, duplicate tiếp theo thấy marker đã tồn tại.

Không để marker ở một database khác với business state nếu không có workflow đồng bộ được thiết kế rõ. Hai DB khác nhau lại tạo dual write mới.

## 26. External provider: state machine cho kết quả không chắc chắn

Một payment operation nên có trạng thái rõ:

~~~text
NEW
 |
 v
REQUESTED
 |
 +--> AUTHORIZED
 |
 +--> DECLINED
 |
 +--> UNKNOWN
        |
        v
    RECONCILING
        |
        +--> AUTHORIZED
        +--> DECLINED
        +--> MANUAL_REVIEW
~~~

UNKNOWN không phải thất bại. Nó có nghĩa không thể xác định outcome chỉ từ response đã nhận. Khi timeout:

1. Giữ nguyên operation ID và provider idempotency key.
2. Không tạo payment attempt mới tùy tiện.
3. Query provider bằng reference/key nếu API hỗ trợ.
4. Nếu provider báo đã xử lý, cập nhật local state.
5. Nếu provider xác nhận chưa nhận, retry cùng key theo contract.
6. Nếu không thể xác định, đưa vào reconciliation/manual review.
7. Audit mọi quyết định và thay đổi state.

Nếu user bấm lại nút thanh toán, API nên trả trạng thái operation hiện tại hoặc hướng dẫn tiếp tục, không mặc định tạo payment operation mới.

## 27. Xử lý idempotency ở API boundary

Duplicate business intent có thể bắt đầu từ client retry trước khi message broker xuất hiện.

Ví dụ:

~~~text
Mobile client sends CreateOrder
       |
       v
Server commits order
       |
       v
Response lost
       |
       v
Client retries CreateOrder
       |
       v
Second order created unless API is idempotent
~~~

API command nên nhận idempotency key do client hoặc server tạo theo contract. Server lưu key và kết quả trong transaction phù hợp; cùng key và cùng request fingerprint trả về kết quả đã xác định. Cùng key nhưng payload khác phải reject.

Khi command tạo outbox event, order row, idempotency record và outbox row cần được ghi cùng transaction nếu ở cùng DB. Như vậy retry từ client không tạo order thứ hai và event thứ hai.

## 28. Exactly-once với email: cần thực tế về giới hạn

Nhiều email providers không có idempotency guarantee giống payment API. Nếu sender gửi email, provider nhận và xếp hàng, nhưng response bị mất, sender không biết email đã được nhận hay chưa.

Các lựa chọn thiết kế:

- Provider có API idempotency/status: dùng theo contract.
- Provider hỗ trợ client message ID: gắn ID ổn định, nhưng xác minh nó có deduplicate thật hay chỉ phục vụ tìm kiếm.
- Lưu delivery intent và trạng thái trước khi gọi.
- Không tạo notification mới khi retry cùng intent.
- Có thể chấp nhận duplicate rất hiếm gặp nếu business impact thấp và provider không hỗ trợ dedup.
- Với thông báo có hậu quả pháp lý/nhạy cảm, thiết kế quy trình kiểm tra hoặc xác nhận bổ sung.

Không tuyên bố “email exactly once” nếu không thể chứng minh provider deduplicate request. Hãy mô tả guarantee thực tế, ví dụ “một delivery intent được tạo duy nhất; provider submission có thể retry; duplicate delivery được giảm thiểu nhưng không thể loại bỏ tuyệt đối theo contract hiện có.”

## 29. Replay không phải xử lý mới

Replay thường dùng để:

- Khôi phục consumer sau bug.
- Xây lại read model/projection.
- Chuyển dữ liệu sang schema mới.
- Reprocess event sau khi sửa lỗi mapping.
- Backfill analytics.

Cần phân loại replay:

1. **Projection rebuild:** tạo read model mới trong store riêng; không phát side effects ra ngoài.
2. **Business reprocessing:** thực hiện lại domain logic; phải giữ idempotency/business keys.
3. **Compensation replay:** phát correction/compensating commands có audit.
4. **Operational retry:** tiếp tục một operation đang pending.
5. **Historical export:** đọc event để phân tích, không làm thay đổi business state.

Một consumer mới với group ID mới có thể đọc toàn bộ history và tạo invoice/payment/email lần nữa nếu side effects không được bảo vệ. Trước replay, xác định side-effect mode, dedup retention, checkpoint và scope.

### 29.1. Dry run

Một replay tool an toàn có thể:

- Chỉ đọc và validate event.
- Ước tính số record/side effects có thể phát sinh.
- Phát hiện event đã xử lý.
- So sánh current state với expected transition.
- Ghi danh sách conflict.
- Yêu cầu approval cho replay có side effects.
- Chạy batch nhỏ trước.
- Dừng theo error/duplicate threshold.

Không mặc định reset offset là thao tác vô hại.

## 30. Retention của idempotency records

Nếu inbox record bị xóa sớm, message cũ được replay có thể tạo side effect lại. Retention cần dựa trên:

- Broker topic retention hoặc queue TTL.
- Retry schedule và maximum elapsed time.
- DLQ retention.
- Manual replay window.
- Disaster recovery restore point.
- External provider idempotency retention.
- Business/legal audit requirements.

Với payment/invoice, có thể cần business ledger hoặc unique reference giữ lâu hơn inbox transient table. Inbox có thể partition/archive, nhưng không được xóa nếu hệ thống còn cho phép replay cùng operation.

Không dùng một TTL ngắn chung cho mọi event. OrderViewed có thể có dedup window ngắn; PaymentCaptured cần invariant và ledger lâu dài.

## 31. Duplicate có thể đến từ nhiều đường

Các nguồn thường gặp:

- Broker redelivery sau crash/rebalance.
- Producer retry sau confirm timeout.
- Outbox relay publish lại.
- Client retry HTTP sau response loss.
- Scheduler chạy job trùng.
- Hai consumer groups cùng thực hiện side effect ngoài ý muốn.
- Operator replay DLQ.
- Event được phát từ CDC và application publisher cùng lúc.
- Disaster recovery restore từ snapshot rồi replay overlap.
- Partner webhook gửi lại callback.
- Hai service cùng nhận một command do routing sai.
- Concurrent workers claim cùng operation.

Một sơ đồ nguồn:

~~~text
Client retry ----\
Producer retry ---\
Outbox relay ------+--> Duplicate delivery/intent --> Consumer
Broker redelivery -/                                |
DLQ replay -------/                                 v
Partner webhook --/                          Idempotency boundary
Scheduler retry --/                                  |
                                                     v
                                              Business effect
~~~

Hãy inventory nguồn duplicate thay vì chỉ tăng max.poll.interval.ms hoặc đổi ACK mode.

## 32. Không nhầm duplicate suppression với business correctness

Nếu consumer thấy event đã xử lý và bỏ qua, điều đó chỉ đúng khi lần xử lý trước thực sự hoàn tất đúng. Nếu trước đó đã ghi marker sai thời điểm hoặc side effect thất bại, dedup có thể che giấu dữ liệu thiếu.

Cần đảm bảo:

- Marker và state change cùng transaction.
- State transition có invariant.
- Unique constraint bảo vệ key nghiệp vụ.
- External provider outcome được lưu/query.
- Reconciliation phát hiện operation pending quá lâu.
- Duplicate metric phân biệt duplicate expected với anomaly.
- Manual override có audit và reason.
- Không xóa marker để “thử lại” mà không biết side effect trước đã xảy ra chưa.

Idempotency là một phần của correctness architecture, không phải middleware checkbox.

## 33. Observability: đo cả delivery lẫn business outcome

Metric cần tách tầng:

| Metric | Ý nghĩa |
|---|---|
| broker_redelivery_total | Số lần broker giao lại |
| consumer_duplicate_event_total | Event ID đã thấy trước đó |
| business_duplicate_suppressed_total | Duplicate intent được chặn bằng business key |
| idempotency_conflict_total | Cùng key nhưng payload/request khác |
| idempotency_in_progress_total | Operation đang được claim/xử lý |
| external_operation_unknown_total | Provider outcome chưa xác định |
| external_operation_reconciled_total | Operation được đối soát thành công |
| outbox_pending_total | Event intent chưa publish |
| oldest_pending_operation_age | Tuổi operation đang chờ |
| dlq_messages_total | Message trong dead-letter path |
| replay_operations_total | Số operation replay |
| business_invariant_violation_total | Vi phạm invariant như invoice/payment duplicate |

Không dùng message ID hoặc customer ID làm metric label cardinality cao. Dùng structured logs/traces với access control để điều tra từng operation.

### 33.1. Alert hữu ích

- Tăng bất thường duplicate suppression sau một release.
- Idempotency key conflict tăng.
- External outcome UNKNOWN vượt thời gian cho phép.
- Payment/invoice pending quá lâu.
- Outbox backlog không giảm.
- DLQ tăng nhanh.
- Broker lag tăng dù producer API trả success.
- Reconciliation phát hiện nhiều record mismatch.
- Duplicate side effect được xác nhận bởi provider/ledger.

Không alert mọi duplicate redelivery như incident nghiêm trọng; at-least-once delivery có thể redeliver bình thường. Alert theo tỷ lệ, xu hướng, loại event và business impact.

## 34. Test failure windows thay vì chỉ test happy path

Một test đơn giản gửi message và assert consumer nhận được không kiểm tra exactly-once business effect. Cần mô phỏng các điểm crash.

### 34.1. Test matrix

| Điểm crash/lỗi | Hành vi mong đợi |
|---|---|
| Trước DB transaction | Broker giao lại; không có state change |
| Trong DB transaction | Rollback; không có marker hoặc business effect |
| Sau DB commit, trước ACK | Redelivery; inbox chặn side effect lặp |
| Sau ACK, trước side effect | Không được xảy ra theo thứ tự thiết kế |
| Sau provider commit, response timeout | Operation UNKNOWN; retry cùng provider key hoặc reconcile |
| Outbox publish rồi crash trước mark | Publish duplicate; consumer dedup |
| Hai worker cùng xử lý | Atomic claim/unique constraint chỉ một business transition |
| DLQ replay sau thời gian dài | Retention/dedup bảo vệ hoặc replay mode không side effect |
| Provider key hết hạn | Không retry mù; reconciliation/manual review |
| DB restore và broker replay overlap | Business ledger/invariants ngăn duplicate |

### 34.2. Test concurrent duplicate

Khởi chạy hai worker xử lý cùng idempotency key đồng thời. Assert:

- Chỉ một operation record được tạo.
- Chỉ một business state transition xảy ra.
- Worker còn lại nhận kết quả existing/in-progress.
- Không có hai provider calls với key khác nhau.
- Database unique constraints giữ invariant kể cả khi application check race.

### 34.3. Test timeout-unknown

Mock provider theo trình tự:

1. Nhận request và commit side effect.
2. Không trả response hoặc làm client timeout.
3. Consumer retry cùng idempotency key.
4. Provider trả lại cùng operation reference.
5. Local DB chỉ ghi một payment operation.
6. Reconciliation xác nhận trạng thái cuối.

Test này quan trọng hơn việc chỉ mock provider ném exception trước khi xử lý request.

## 35. Ví dụ kiểm thử idempotent consumer

Một test có thể gửi cùng event hai lần:

~~~java
@Test
void duplicateEventCreatesOnlyOneInvoice() {
    OrderPlacedEvent event = testOrderPlacedEvent();

    handler.handle(event);
    handler.handle(event);

    assertThat(invoiceRepository.countByOrderId(event.orderId()))
        .isEqualTo(1);

    assertThat(inboxRepository.countByEventId(event.eventId()))
        .isEqualTo(1);
}
~~~

Đây là skeleton test. Cần chạy với database transaction thực tế hoặc test container để xác minh unique constraint, rollback và concurrency. Unit test mock repository không chứng minh race condition được xử lý ở DB.

Test crash window nên inject failure sau commit nhưng trước ACK trong integration test với broker thật/test container. Kiểm tra sau redelivery rằng invoice count vẫn là một và message cuối cùng được ACK/offset commit.

## 36. Runbook xử lý duplicate side effect

Khi phát hiện duplicate payment/invoice/email:

1. **Contain:** tạm dừng consumer hoặc giảm concurrency theo playbook nếu duplicate đang tiếp diễn.
2. **Preserve evidence:** giữ event IDs, business operation IDs, provider references và timeline.
3. **Determine scope:** xác định tenant, time window, consumer version, topic/queue và replay batch.
4. **Check broker:** redelivery, retry, rebalance, duplicate producer publish hay operator replay.
5. **Check inbox/idempotency:** marker có được commit cùng business state không? Có key conflict không?
6. **Check external provider:** query operation/reference; không tự refund/void chỉ dựa vào local timeout.
7. **Reconcile:** so sánh database, provider ledger, invoice và business records.
8. **Mitigate:** chặn command/replay trùng; giữ idempotency key ổn định.
9. **Compensate:** refund/void/cancel/correction theo domain policy và approval.
10. **Verify:** đối chiếu invariant sau mitigation.
11. **Fix:** bổ sung atomic claim, unique constraint, outbox/inbox hoặc provider key.
12. **Replay safely:** chỉ replay sau khi dedup và side-effect mode được xác minh.
13. **Document:** ghi root cause, affected operations, recovery evidence và follow-up owner.

Không sửa/xóa audit records để làm mất dấu vết. Compensation là một business action mới, cần liên kết với operation ban đầu.

## 37. Ví dụ: xử lý invoice trùng

Giả sử Billing Service nhận cùng OrderPlaced hai lần và tạo hai invoice.

Điều tra:

- Cùng eventId hay hai event IDs khác nhau?
- Consumer group có thay đổi hoặc offset reset không?
- Process crash sau DB commit trước ACK?
- Inbox marker có cùng transaction với invoice insert không?
- Unique constraint trên order reference có tồn tại không?
- Có hai consumer groups cùng gọi Billing side effect không?
- Outbox relay có publish lại sau crash?
- Manual replay có bypass dedup không?

Khắc phục:

- Nếu hai event IDs khác nhau nhưng cùng một invoice intent, bổ sung unique business key.
- Nếu marker commit tách transaction, gộp vào transaction business.
- Nếu nhiều consumer groups cùng tạo invoice, xác định một owner và command routing.
- Nếu replay là nguyên nhân, yêu cầu replay mode và audit.
- Với invoice đã phát hành, dùng credit note/correction theo quy trình kế toán; không xóa bản ghi lịch sử.

## 38. Ví dụ: xử lý payment UNKNOWN

Một consumer gửi authorize request và timeout. Không có response.

Không nên:

~~~text
Timeout
  |
  v
Generate new payment ID
  |
  v
Retry new charge
~~~

Nên:

~~~text
Timeout
  |
  v
Keep same paymentOperationId
  |
  v
Query provider by stable key/reference
  |
  +--> Found authorized -> persist AUTHORIZED
  |
  +--> Found declined -> persist DECLINED
  |
  +--> Not found with definitive provider semantics
  |        -> retry same key if allowed
  |
  +--> Cannot determine
           -> remain UNKNOWN / manual reconciliation
~~~

Nếu provider không hỗ trợ lookup, cần xem hợp đồng idempotency, thời gian lưu key và quy trình đối soát. Không tự giả định một response timeout có nghĩa provider chưa xử lý.

## 39. Retention, privacy và audit

Idempotency ledger có thể chứa payment references, order IDs, tenant references và trạng thái nghiệp vụ. Nó cần access control, retention và data minimization phù hợp.

- Không lưu raw card data, password, token hoặc secret.
- Dùng reference thay cho PII khi có thể.
- Bảo vệ idempotency keys khỏi lộ nếu chúng có thể được dùng để truy cập kết quả.
- Giới hạn ai có thể query/export ledger.
- Không xóa record trước khi hết retry/replay window.
- Lưu audit cho manual replay, override, refund và correction.
- Có retention riêng cho inbox transient markers và business financial ledger.
- Đảm bảo backup/restore không tạo overlap khiến replay side effect.

Idempotency table không nhất thiết là audit log đầy đủ; nếu cần giải trình, lưu event/audit record theo policy riêng.

## 40. Checklist thiết kế theo loại side effect

| Side effect | Idempotency boundary phù hợp | Bằng chứng cuối |
|---|---|---|
| Insert invoice | Unique business reference + inbox transaction | Một invoice theo invariant |
| Update order status | Aggregate version + conditional update | State/version hợp lệ |
| Reserve inventory | Reservation request ID + unique reservation | Một reservation cho intent |
| Authorize payment | Provider idempotency key + local operation ledger | Provider operation reference |
| Send email | Notification intent key + provider support nếu có | Submission/delivery status |
| Webhook outbound | Stable delivery ID + receiver dedup contract | Receiver acknowledgement/status |
| Update search projection | Event ID/version + rebuildable projection | Projection version/checkpoint |
| Analytics aggregate | Batch/run ID + idempotent upsert | Reconciliation totals |
| Generate document | Business document key + unique record | Một artifact logical/version |
| External partner command | Partner request key + status query/reconciliation | Partner operation reference |

Không áp cùng một pattern cho mọi side effect. Database insert có unique constraint; payment cần provider contract; email có thể không thể bảo đảm tuyệt đối; projection có thể rebuild; business saga cần compensation.

## 41. Những sai lầm phổ biến

1. **Cho rằng broker bảo đảm mọi tác dụng phụ chỉ xảy ra một lần:** broker không bao trùm DB và external systems.
2. **Bật producer idempotence rồi bỏ consumer dedup:** producer retry không giải quyết consumer redelivery.
3. **ACK trước DB commit:** crash làm mất business effect.
4. **Commit DB rồi ACK nhưng không idempotent:** crash window tạo side effect trùng.
5. **Ghi inbox marker riêng transaction:** marker có thể tồn tại dù business update thất bại.
6. **Chỉ dedup theo eventId:** hai event IDs có thể cùng business intent.
7. **Sinh idempotency key mới khi retry:** provider coi đó là operation mới.
8. **Dùng orderId làm key cho mọi thao tác:** chặn nhầm nhiều payment/refund hợp lệ.
9. **Retry provider sau timeout mà không query trạng thái:** có thể charge hai lần.
10. **Coi timeout là failure final:** kết quả có thể đã commit ở phía nhận.
11. **Coi timeout là success:** có thể bỏ sót side effect chưa được thực hiện.
12. **Dùng synchronized trong một JVM:** không bảo vệ nhiều replicas.
13. **Chỉ kiểm tra tồn tại trước khi insert:** race condition vẫn tạo duplicate.
14. **Không có unique constraint:** application bug có thể phá invariant.
15. **Xóa inbox markers quá sớm:** DLQ replay tạo side effect cũ.
16. **Đổi consumer group rồi replay toàn bộ:** side effect lịch sử có thể lặp.
17. **Cho rằng Kafka EOS bao trùm PostgreSQL/payment:** transaction boundary bị hiểu sai.
18. **Cho rằng Rabbit publisher confirm bảo đảm consumer effect:** confirm chỉ ở phía publish.
19. **Cho rằng ordering loại bỏ duplicate:** ordering và idempotency là hai vấn đề khác nhau.
20. **Replay DLQ không kiểm tra side effect đã xảy ra:** tạo invoice/payment/email trùng.
21. **Không có trạng thái UNKNOWN:** workflow bị ép thành success/failure dù evidence không đủ.
22. **Không đối soát provider:** pending/duplicate operation tồn tại lâu.
23. **Không quan sát duplicate suppression:** bất thường bị che giấu.
24. **Chỉ test happy path:** không thử crash-after-commit và timeout-unknown.
25. **Tuyên bố email exactly once khi provider không hỗ trợ:** guarantee vượt quá khả năng chứng minh.
26. **Không phân biệt transport retry và business retry:** tạo operation ID mới ngoài ý muốn.
27. **Không audit manual override:** mất dấu vết xử lý duplicate.
28. **Coi compensation là rollback:** refund/correction là side effect mới và cũng cần idempotency.

## 42. Checklist triển khai

- [ ] Xác định exactly-once đang nói về delivery, processing, DB state hay external business effect.
- [ ] Vẽ transaction boundary và failure windows cho từng bước.
- [ ] Dùng outbox khi cần gắn business commit với event publish.
- [ ] Dùng inbox/processed-message marker cho consumer.
- [ ] Marker và business DB side effect nằm trong cùng transaction.
- [ ] Có unique constraints bảo vệ business invariants.
- [ ] Phân biệt eventId, commandId và business operation ID.
- [ ] Idempotency key ổn định qua retries/restarts.
- [ ] Cùng key nhưng payload khác được xử lý như conflict.
- [ ] Atomic claim xử lý concurrency nhiều replicas.
- [ ] ACK/offset commit sau khi business transaction hoàn tất.
- [ ] External provider có idempotency/status query khi khả thi.
- [ ] Timeout tạo UNKNOWN state và reconciliation path.
- [ ] Retry có giới hạn, backoff, jitter và không tạo key mới.
- [ ] DLQ replay kiểm tra side effects và dedup retention.
- [ ] Retention bao phủ broker/DLQ/replay/provider windows.
- [ ] Ordering dùng aggregate version khi nghiệp vụ yêu cầu.
- [ ] Saga compensation cũng idempotent.
- [ ] Có metrics duplicate, idempotency conflict, UNKNOWN và reconciliation.
- [ ] Có test crash-after-commit, timeout-unknown và concurrent duplicate.
- [ ] Có runbook containment, investigation, compensation và replay.
- [ ] Guarantee được mô tả đúng phạm vi, không tuyên bố exactly-once toàn hệ thống.

## 43. Bài tập tình huống

Một hệ thống thương mại điện tử có Order Service, Billing Service và Notification Worker. Order Service ghi order vào PostgreSQL và phát OrderPlaced. Billing tạo invoice rồi gọi payment provider. Notification gửi email xác nhận.

Một lần deploy mới xảy ra sự cố:

- Billing nhận OrderPlaced.
- Invoice được commit thành công.
- Pod bị kill trước khi Kafka offset được commit.
- Message được giao lại.
- Payment provider nhận hai request.
- Notification worker cũng gửi email lại sau timeout.
- API Order vẫn trả 201 cho client.

### Câu hỏi

1. Vì sao producer/broker guarantee không ngăn invoice trùng?
2. Failure window nào tạo duplicate billing?
3. Inbox marker cần được ghi ở đâu so với invoice?
4. Nếu hai event IDs khác nhau cùng đại diện một order payment intent thì dedup bằng gì?
5. Payment provider đã commit nhưng response timeout; consumer nên lưu trạng thái nào?
6. Khi retry payment, idempotency key có thay đổi không?
7. Email provider không hỗ trợ idempotency; có thể tuyên bố guarantee nào?
8. Nếu DLQ replay sau 7 ngày, inbox marker còn tồn tại không?
9. Những metric/alert nào phát hiện vấn đề sớm?
10. Cần test nào để tái hiện crash sau invoice commit nhưng trước offset commit?

### Gợi ý phân tích

- Broker redelivery là hành vi at-least-once; consumer handler có thể chạy nhiều lần.
- Inbox marker và invoice insert phải cùng DB transaction; unique constraint theo business invoice reference là lớp bảo vệ bổ sung.
- Payment cần operation ID và provider idempotency key ổn định; timeout tạo UNKNOWN, sau đó query/reconcile.
- Email submission có thể retry theo delivery intent, nhưng guarantee phụ thuộc provider; nếu không có dedup thì không hứa tuyệt đối.
- Inbox/dedup retention phải bao phủ DLQ replay window hoặc replay phải chạy ở mode không phát side effect.
- Theo dõi duplicate suppression, payment UNKNOWN age, invoice uniqueness conflicts, DLQ, consumer lag và reconciliation mismatch.
- Integration test phải kill consumer sau DB commit, trước ACK/offset commit rồi xác nhận redelivery không tạo side effect thứ hai.

## 44. Bài tập thực hành: xây consumer idempotent

Triển khai handler cho event PaymentAuthorized:

1. Validate schema và producer identity.
2. Lấy eventId, paymentOperationId và aggregate version.
3. Atomic claim inbox record theo consumer name + event ID.
4. Kiểm tra business operation key và state hiện tại.
5. Nếu operation đã hoàn tất, trả kết quả existing mà không gọi provider lại.
6. Nếu cần external action, dùng stable provider idempotency key.
7. Lưu trạng thái REQUESTED/UNKNOWN/CONFIRMED theo outcome.
8. Ghi event tiếp theo vào outbox trong cùng transaction với state change.
9. Commit database.
10. ACK/commit offset sau khi transaction hoàn tất.
11. Retry transient failure theo policy; invalid/permanent errors đi quarantine/DLQ.
12. Có reconciliation job cho UNKNOWN hoặc pending quá lâu.

Test tối thiểu:

- Cùng event gửi hai lần chỉ tạo một business transition.
- Hai event IDs khác nhau nhưng cùng operation key không tạo hai payment.
- Hai worker cùng claim một key không thể cùng thực hiện side effect.
- Crash sau DB commit trước ACK không tạo duplicate.
- Provider commit nhưng response timeout dẫn đến UNKNOWN và query/retry cùng key.
- Cùng idempotency key nhưng payload khác bị reject.
- DLQ replay không bypass inbox/unique constraints.
- Inbox transaction rollback không để lại marker giả.
- Retention không xóa marker trước replay window.
- Reconciliation sửa được pending state mà không tạo operation mới.

## 45. Kết luận

Message broker có thể cung cấp durability, producer idempotence, transactions, ACK/offset và redelivery theo những phạm vi cụ thể. Những cơ chế đó rất quan trọng, nhưng **không tự bảo đảm mọi tác dụng phụ ở database, payment provider, email, webhook và các service khác chỉ xảy ra một lần**.

Thiết kế đáng tin bắt đầu bằng việc xác định transaction boundary và failure windows. Với database consumer, dùng inbox marker và business state trong cùng transaction, kết hợp unique constraints. Với producer, dùng transactional outbox để event intent được commit cùng business change. Với external provider, giữ idempotency key ổn định, lưu operation state và đối soát kết quả không chắc chắn. Với workflow nhiều service, dùng Saga, compensation và reconciliation.

**Hãy thiết kế để message có thể được giao và xử lý lặp lại mà business outcome vẫn đúng.** Đó là một bảo đảm thực tế, có thể kiểm thử và vận hành, thay vì dựa vào lời hứa exactly-once chung chung.
