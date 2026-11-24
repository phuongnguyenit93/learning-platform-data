# Phân biệt bảo đảm giao nhận với bảo đảm tác động nghiệp vụ

Một message được broker giao thành công không đồng nghĩa nghiệp vụ đã được thực hiện đúng một lần. Một consumer có thể ghi database rồi chết trước khi ACK; broker sẽ giao lại message và consumer có thể chạy lại. Ngược lại, nếu consumer ACK trước khi commit dữ liệu, message có thể bị broker loại bỏ dù nghiệp vụ chưa hoàn tất.

Khi tích hợp Spring Boot với Azure Service Bus, Event Hubs, AWS SQS, Kinesis hoặc Google Cloud Pub/Sub, cần phân biệt hai câu hỏi:

- **Bảo đảm giao nhận (delivery guarantee):** broker và client phối hợp để message được giao, giữ, retry hoặc xác nhận như thế nào?
- **Bảo đảm tác động nghiệp vụ (business-effect guarantee):** trạng thái database, khoản thanh toán, file, email hoặc hành động bên ngoài có được áp dụng đúng một lần theo ý nghĩa nghiệp vụ hay không?

Broker có thể cung cấp at-most-once, at-least-once hoặc một chế độ exactly-once trong phạm vi cụ thể. Nhưng một side effect nghiệp vụ thường đi qua nhiều hệ thống và transaction boundary khác nhau. Muốn đạt hành vi **effectively-once**, ứng dụng phải kết hợp delivery semantics với idempotency, transaction, inbox/outbox, deduplication và reconciliation.

Bài thuộc chương **Độ tin cậy** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt at-most-once, at-least-once, exactly-once delivery và effectively-once business effect.
2. Tách các mốc publish, broker acceptance, delivery, processing, commit, side effect và ACK.
3. Giải thích vì sao ACK trước commit có thể làm mất nghiệp vụ, còn commit trước ACK có thể tạo redelivery.
4. Thiết kế consumer idempotent bằng inbox table, unique constraint và transaction.
5. Kết hợp transactional outbox với publisher retry và message ID ổn định.
6. Hiểu phạm vi của Azure Service Bus/Event Hubs, AWS SQS/Kinesis và Google Cloud Pub/Sub.
7. Nhận biết exactly-once delivery không tự tạo exactly-once cho database, payment, email hoặc dịch vụ ngoài broker.
8. Xử lý message lock, visibility timeout, ack deadline, checkpoint, ordering và dead-letter queue.
9. Thiết kế replay, reconciliation và xử lý poison message an toàn.
10. Kiểm thử crash window, duplicate delivery, lost ACK và business side effect bằng failure injection.

## 2. Hai lớp bảo đảm cần tách riêng

Một luồng message thường có các bước:

~~~text
Producer tạo event
    → Publish request
    → Broker chấp nhận và lưu message
    → Broker giao message cho consumer
    → Consumer chạy handler
    → Consumer tạo side effect
    → Consumer commit trạng thái bền vững
    → Consumer ACK/Complete message
~~~

Mỗi mũi tên có thể thất bại độc lập. Ví dụ broker đã lưu message nhưng publisher không nhận được confirmation; consumer đã commit database nhưng ACK bị mất; hoặc API payment đã xử lý yêu cầu nhưng response timeout.

| Lớp | Bảo đảm cần xem xét | Thành phần kiểm soát chính |
| --- | --- | --- |
| Publish | Message đã được broker chấp nhận chưa? | Producer SDK, broker confirmation, retry và message ID |
| Delivery | Message được giao tối đa/một lần hay ít nhất/một lần? | Broker, subscription/queue, lock/visibility/ack |
| Processing | Handler có thể chạy lại không? | Consumer, worker lifecycle, retry/redelivery |
| Persistence | Trạng thái nghiệp vụ đã commit chưa? | Database transaction, unique constraint, conditional write |
| External side effect | Payment/email/API/file đã xảy ra chưa? | Provider idempotency, operation reference, reconciliation |
| ACK/checkpoint | Broker có được báo rằng message đã xử lý không? | Consumer settlement/ack/checkpoint |

**Delivery guarantee không phải business-effect guarantee.** Broker chỉ biết trạng thái message theo giao thức của nó. Broker thường không thể biết transaction database của ứng dụng đã commit hay payment provider đã trừ tiền hay chưa.

## 3. Ba mô hình delivery phổ biến

### 3.1. At-most-once delivery

Message được giao tối đa một lần trong phạm vi semantics đã chọn. Nếu có lỗi tại thời điểm không thuận lợi, message có thể bị mất hoặc không được xử lý lại.

Đặc điểm:

- Tránh redelivery/duplicate ở phạm vi delivery được định nghĩa.
- Có thể bỏ sót message nếu consumer hoặc ACK path gặp lỗi.
- Phù hợp khi mất một số event có thể chấp nhận hoặc dữ liệu có thể tái tạo.
- Không phù hợp với nghiệp vụ cần bảo đảm mọi yêu cầu đều được xử lý.

Ví dụ: consumer nhận message theo chế độ receive-and-delete. Broker loại message khỏi queue khi giao; nếu process chết ngay sau khi nhận, message không còn để giao lại.

### 3.2. At-least-once delivery

Broker tiếp tục giao lại cho tới khi nhận được ACK/Complete hợp lệ hoặc message đi tới trạng thái hết hạn/DLQ theo policy.

Đặc điểm:

- Giảm nguy cơ mất message khi consumer crash.
- Message có thể được giao nhiều lần.
- Consumer phải chịu được duplicate delivery.
- Đây là mô hình phổ biến ở nhiều queue/broker managed.

Ví dụ: consumer nhận message, ghi database rồi crash trước khi complete. Lock/visibility/ack deadline hết hạn; broker giao lại message.

### 3.3. Exactly-once delivery

Một dịch vụ có thể cung cấp tính năng exactly-once trong phạm vi cụ thể, chẳng hạn nhận message hoặc xử lý một luồng trong một subscription/transaction boundary được hỗ trợ.

Cần hỏi chính xác:

- Exactly-once áp dụng cho producer publish, broker storage, consumer delivery hay stream processing?
- Phạm vi là queue, subscription, partition, session hay transaction?
- Cửa sổ deduplication/retention kéo dài bao lâu?
- Điều kiện region, protocol, client library và cấu hình là gì?
- ACK/commit có phải được xác nhận thành công trước khi broker coi message đã hoàn tất?
- Có bao gồm database hoặc external API mà consumer gọi không?

Không suy ra rằng tính năng có chữ **exactly-once** bảo đảm toàn bộ tác động nghiệp vụ end-to-end.

### So sánh nhanh

| Delivery model | Có thể mất message? | Có thể giao trùng? | Consumer cần idempotent? |
| --- | --- | --- | --- |
| At-most-once | Có, tùy failure/settlement semantics | Theo delivery contract thường không redeliver | Vẫn cần nếu producer hoặc side effect có thể lặp |
| At-least-once | Hạn chế mất sau khi broker đã nhận; vẫn phụ thuộc retention/DLQ/config | Có | Có |
| Exactly-once delivery trong phạm vi hỗ trợ | Hạn chế duplicate delivery trong phạm vi được định nghĩa | Có thể còn duplicate ngoài phạm vi đó hoặc khi app side effect lặp | Có, đặc biệt khi có external side effect |
| Effectively-once business effect | Mục tiêu là một kết quả nghiệp vụ quan sát được | Request/message có thể vẫn được giao hoặc xử lý lại | Được bảo vệ bằng idempotency/transaction/reconciliation |

## 4. Delivery, processing và business effect là ba việc khác nhau

Ví dụ consumer xử lý event OrderPaid:

1. Broker giao event.
2. Consumer đọc message.
3. Consumer ghi trạng thái đơn hàng thành PAID.
4. Consumer gửi email xác nhận.
5. Consumer ACK message.

Nếu consumer crash ở từng thời điểm, kết quả khác nhau:

| Thời điểm crash | Trạng thái có thể xảy ra | Rủi ro |
| --- | --- | --- |
| Trước khi handler bắt đầu | Chưa có side effect | Broker có thể giao lại |
| Sau khi đọc message, trước commit | Chưa commit nghiệp vụ | Redelivery thường an toàn nếu handler chưa gọi external side effect |
| Sau database commit, trước ACK | Database đã thay đổi | Redelivery có thể cập nhật/gửi email lần nữa |
| Sau email, trước database commit | Email đã gửi, database chưa ghi | Retry có thể gửi email trùng |
| Sau ACK, trước side effect | Broker coi message hoàn tất | Nghiệp vụ có thể bị mất vĩnh viễn |
| Sau khi external provider xử lý nhưng response bị mất | Kết quả không xác định với consumer | Retry mù có thể tạo side effect lần hai |

Điểm khó nhất là **khoảng thời gian giữa side effect và ACK**. Broker và database thường không tham gia cùng một distributed transaction. Consumer phải thiết kế để chịu được crash ở mọi ranh giới.

## 5. ACK trước hay sau khi commit?

### ACK trước commit: nguy cơ mất tác động nghiệp vụ

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Database
    B->>C: Deliver message M1
    C->>B: ACK / Complete
    B-->>C: Message settled
    C->>DB: Write business state
    Note over C,DB: Process crash trước commit
    Note over B: Broker không giao lại message
    Note over DB: Business state chưa được ghi
~~~

Nếu ACK trước khi side effect bền vững hoàn tất, broker có thể loại message khỏi queue trong khi nghiệp vụ chưa được commit. Với at-least-once queue, cách làm phổ biến là **commit trước rồi mới ACK**.

### Commit trước ACK: có thể duplicate nhưng có thể kiểm soát

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Database
    B->>C: Deliver message M1
    C->>DB: BEGIN + update business + inbox
    DB-->>C: COMMIT
    C->>B: ACK / Complete
    Note over C,B: ACK bị mất hoặc process crash
    B->>C: Redeliver M1
    C->>DB: Insert inbox M1
    DB-->>C: Duplicate key
    C->>B: ACK duplicate, không lặp business effect
~~~

Đây là mô hình thường dùng với **inbox pattern**. Database commit trước; nếu ACK thất bại, broker giao lại nhưng inbox unique constraint ngăn chạy business update lần nữa.

### Quy tắc

- Với consumer xử lý database, ghi inbox và business state trong cùng transaction, commit rồi ACK.
- Không ACK message chỉ vì handler đã bắt đầu hoặc đã đưa công việc vào thread pool.
- Nếu chuyển công việc sang background queue nội bộ, phải lưu trạng thái tiếp nhận bền vững trước khi ACK message gốc.
- Nếu side effect là hệ thống ngoài database, cần idempotency key của provider, outbox/saga hoặc reconciliation.
- ACK thất bại sau commit là tình huống bình thường cần thiết kế; không được coi là một lỗi hiếm có thể bỏ qua.

## 6. Vì sao exactly-once end-to-end rất khó?

Giả sử một consumer cần:

1. Ghi database.
2. Trừ tiền ở payment provider.
3. Gửi email.
4. Complete message.

Các hệ thống này không chia sẻ một transaction nguyên tử. Không có một commit duy nhất có thể đồng thời khóa tất cả side effect.

~~~mermaid
flowchart LR
    M[Broker message] --> C[Spring Boot consumer]
    C --> D[(Database)]
    C --> P[Payment provider]
    C --> E[Email provider]
    C --> A[Broker ACK]
    D -. transaction riêng .- P
    P -. API riêng .- E
    E -. không cùng transaction .- A
~~~

Các tình huống:

- Payment provider đã trừ tiền, nhưng consumer mất response.
- Database commit thành công, email provider timeout.
- Email đã gửi, nhưng consumer crash trước ACK.
- ACK thành công nhưng database transaction chưa commit nếu thứ tự sai.
- Consumer retry sau khi không biết payment đã thành công hay chưa.

Muốn bảo đảm một kết quả nghiệp vụ, cần định nghĩa **invariant** và cách kiểm soát từng side effect. Một hệ thống thường đạt **effectively-once** bằng:

- Idempotency key ổn định xuyên suốt retry.
- Unique constraint/conditional write ở nơi lưu trạng thái.
- Transactional outbox/inbox.
- API provider hỗ trợ idempotency key.
- State machine/saga và compensation.
- Reconciliation khi kết quả không xác định.
- ACK/checkpoint chỉ sau khi trạng thái cần bảo vệ đã bền vững.

Không có một annotation Spring hoặc một flag broker nào tự tạo exactly-once cho toàn bộ các hệ thống này.

## 7. Effectively-once: bảo đảm kết quả quan sát được

**Effectively-once** là mục tiêu thiết kế: dù message hoặc request có thể được giao/gọi lại nhiều lần, hệ thống vẫn tạo ra một kết quả nghiệp vụ duy nhất theo invariant đã định.

Ví dụ: event OrderPaid có thể được giao 3 lần nhưng:

- Bảng order chỉ chuyển sang PAID một lần.
- Ledger chỉ ghi một transaction với business reference duy nhất.
- Email được gửi theo một notification operation ID có deduplication.
- Consumer có thể ACK các bản giao lại mà không lặp side effect.

Để đạt được điều đó, cần phân biệt:

| Thành phần | Cách bảo vệ |
| --- | --- |
| Business state trong database | Unique constraint, transaction, conditional update |
| Event/command identity | Event ID hoặc idempotency key ổn định |
| Consumer processing | Inbox/processed-message record |
| Publish intent | Transactional outbox |
| External API | Provider idempotency key hoặc tra cứu operation reference |
| Storage object | Deterministic object key, ETag/generation precondition |
| Recovery | State machine, DLQ, reconciliation và replay có kiểm soát |

**Effectively-once không có nghĩa message chỉ được giao một lần.** Nó có nghĩa việc giao lặp không làm thay đổi kết quả nghiệp vụ ngoài ý muốn.

## 8. Inbox pattern: bảo vệ consumer database transaction

Inbox là bảng lưu những message consumer đã xử lý. Khóa duy nhất thường gồm consumer name và message ID để cùng một message có thể được xử lý bởi các consumer logic khác nhau nếu cần.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(120) NOT NULL,
    message_id    VARCHAR(200) NOT NULL,
    payload_hash  VARCHAR(64) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    result_ref    VARCHAR(200),
    PRIMARY KEY (consumer_name, message_id)
);
~~~

### Flow xử lý

1. Nhận message với event ID ổn định.
2. Chuẩn hóa payload và tính fingerprint nếu cần.
3. Bắt đầu transaction database.
4. Insert inbox record.
5. Nếu unique conflict:
   - Đọc fingerprint đã lưu.
   - Nếu fingerprint giống nhau, đây là redelivery của cùng event; bỏ qua business update.
   - Nếu fingerprint khác nhau, phát hiện producer tái sử dụng message ID sai; đưa vào xử lý lỗi/điều tra.
6. Nếu insert thành công, áp dụng business state transition.
7. Commit inbox và business state cùng transaction.
8. ACK/Complete message sau commit.

### Sơ đồ transaction

~~~text
BEGIN
  INSERT processed_messages(consumer_name, message_id, payload_hash)
  UPDATE orders / INSERT ledger / UPDATE business state
COMMIT

ACK message
~~~

Nếu transaction rollback, inbox record và business update cùng rollback. Khi broker giao lại, consumer có thể xử lý lại. Nếu transaction commit nhưng ACK thất bại, lần giao lại bị inbox chặn.

### Consumer phải có scope rõ ràng

Không nên dùng message ID một mình nếu cùng broker/namespace có nhiều producer hoặc nhiều consumer. Scope có thể là:

~~~text
(consumer_name, event_id)
~~~

Nếu một event có nhiều phiên bản schema, fingerprint cần tính theo payload đã chuẩn hóa và version. Không coi cùng event ID với payload khác là duplicate hợp lệ.

## 9. Transactional outbox: bảo vệ producer

Outbox bảo vệ ranh giới giữa transaction nghiệp vụ và publish message.

Giả sử Order API cập nhật database và cần phát OrderCreated:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT orders(...)
  INSERT outbox_events(event_id, event_type, payload, status)
COMMIT

Publisher worker:
  Claim pending outbox event
  Publish with stable event_id as message ID
  Mark sent after broker confirmation
~~~

Nếu database commit nhưng broker unavailable, event vẫn nằm trong outbox. Publisher có thể thử lại sau. Nếu broker đã nhận nhưng confirmation bị mất, publisher có thể gửi lại cùng event ID; consumer inbox hoặc broker duplicate detection xử lý duplicate.

### Outbox không bảo đảm publish đúng một lần

Có một khoảng hở:

1. Broker nhận message.
2. Publisher mất confirmation hoặc crash.
3. Outbox record vẫn là PENDING.
4. Publisher chạy lại và gửi cùng event lần nữa.

Vì vậy outbox thường bảo đảm **không mất ý định publish** khi database commit, nhưng vẫn có thể phát duplicate. Dùng event ID ổn định, consumer inbox và idempotency để đạt effectively-once.

### Claim event giữa nhiều publisher

Publisher nhiều replica cần claim record atomic, ví dụ database row lock, câu lệnh **FOR UPDATE SKIP LOCKED**, hoặc lease có owner token/expiry. Tuy nhiên claim không loại bỏ mọi duplicate: publisher có thể mất lease trong lúc publish, broker đã nhận message, worker mới claim lại. Consumer vẫn phải deduplicate.

## 10. Event identity: message ID, event ID và correlation ID

Các ID này có mục đích khác nhau:

| ID | Mục đích | Có ổn định khi retry? |
| --- | --- | --- |
| **Event ID** | Định danh một sự kiện nghiệp vụ đã phát sinh | Có |
| **Message ID** | Định danh message trong broker | Nên có, thường lấy từ event ID |
| **Idempotency key** | Định danh một ý định/command có thể được gửi lại | Có |
| **Correlation ID** | Liên kết các bước của một workflow/request | Có thể giữ xuyên workflow |
| **Trace ID** | Quan sát một trace execution | Có thể khác khi redelivery/replay tùy tracing strategy |
| **Delivery count** | Số lần broker đã giao message | Thay đổi theo lần giao |

Không dùng trace ID làm deduplication key: trace mới có thể được tạo khi message redelivery. Không tạo message ID mới mỗi lần publisher retry. Không dùng delivery count làm business identity.

### Event ID ổn định

Producer nên tạo event ID khi ghi business event/outbox và lưu cùng transaction. Mọi lần publish lại cùng event phải sử dụng cùng ID. Nếu event là một phần của aggregate, có thể kết hợp aggregate ID và event sequence/version để phát hiện event trùng hoặc sai thứ tự.

## 11. Azure Service Bus: lock và settlement không đồng nghĩa exactly-once

Azure Service Bus có các receive mode và settlement semantics khác nhau.

### Peek-Lock

- Broker giữ message và cấp lock cho consumer.
- Consumer xử lý message.
- Consumer gọi Complete khi xử lý xong.
- Nếu consumer Abandon, lock hết hạn hoặc process chết, message có thể được giao lại.
- Lock duration và auto-renew có giới hạn theo cấu hình/dịch vụ.
- Delivery count tăng theo redelivery; vượt MaxDeliveryCount có thể chuyển message vào dead-letter queue.

Đây là mô hình hỗ trợ **at-least-once processing**. Consumer phải idempotent.

### Receive-and-Delete

Broker xóa message khi giao cho consumer theo semantics của mode này. Nếu process chết sau khi nhận nhưng trước khi xử lý xong, message có thể bị mất. Đây là lựa chọn khi ứng dụng chấp nhận khả năng mất message để giảm settlement round-trip.

Không dùng Receive-and-Delete cho payment/order/command cần bảo đảm xử lý bền vững trừ khi có cơ chế tái tạo/reconciliation riêng.

### Duplicate detection

Service Bus có tính năng duplicate detection dựa trên MessageId trong cửa sổ được cấu hình:

- Giúp broker bỏ qua một số lần gửi trùng cùng MessageId trong phạm vi entity/cửa sổ.
- Không phải kho deduplication vô thời hạn.
- Message gửi lại sau cửa sổ hoặc có ID khác có thể được coi là message mới.
- Không bảo vệ side effect consumer đã thực hiện ở database hoặc API ngoài broker.

Vẫn nên dùng inbox/unique constraint ở consumer cho nghiệp vụ quan trọng.

### Sessions và ordering

Sessions có thể hỗ trợ xử lý tuần tự theo session và session lock. Điều này giúp ordering trong một session theo semantics Service Bus, nhưng không tạo global ordering giữa mọi message trong queue. Một session lock hết hạn vẫn có thể dẫn tới redelivery.

## 12. Azure Event Hubs: checkpoint là mốc tiến độ, không phải transaction nghiệp vụ

Event Hubs là event streaming service, không phải queue settlement theo mô hình Complete từng message giống Service Bus.

- Event được ghi vào partition.
- Consumer đọc theo offset/sequence trong partition.
- Consumer lưu checkpoint để ghi nhận vị trí đã xử lý.
- Khi consumer restart/rebalance, nó tiếp tục từ checkpoint đã lưu.
- Nếu business state đã commit nhưng checkpoint chưa được lưu, event có thể được đọc lại.
- Nếu checkpoint được lưu trước business commit, event có thể bị bỏ qua dù side effect chưa hoàn tất.

### Thứ tự commit và checkpoint

Với consumer cần cập nhật database:

~~~text
Read event at offset 120
  → Begin DB transaction
  → Insert inbox(event_id) + update business state
  → Commit DB
  → Save Event Hubs checkpoint at offset 120
~~~

Nếu process crash sau DB commit nhưng trước checkpoint, event có thể được đọc lại; inbox chặn duplicate. Nếu checkpoint trước DB commit, crash có thể làm mất tác động nghiệp vụ.

Checkpoint thường được lưu theo partition và consumer group. Không coi một checkpoint thành công là bằng chứng tất cả side effect bên ngoài đã commit nếu code cập nhật checkpoint quá sớm.

### Partition ordering

Event Hubs bảo đảm thứ tự trong một partition theo log/offset, không phải global order giữa tất cả partition. Nếu nghiệp vụ cần thứ tự theo aggregate, producer cần chọn partition key phù hợp và consumer phải xử lý version/sequence.

## 13. AWS SQS và Kinesis

### SQS Standard

- Cung cấp at-least-once delivery; duplicate có thể xảy ra.
- Visibility timeout ẩn message sau khi receive trong một khoảng thời gian.
- Consumer xóa message sau khi xử lý thành công.
- Nếu visibility timeout hết trước khi delete, message có thể được giao lại.
- DLQ/redrive policy xử lý message vượt số lần nhận theo cấu hình.

Consumer nên commit business state và inbox trước khi delete message. Nếu delete thất bại sau commit, redelivery phải được inbox nhận diện.

### SQS FIFO

FIFO hỗ trợ ordering theo message group và deduplication ID trong một cửa sổ deduplication được dịch vụ định nghĩa. Tính năng này giúp giảm duplicate publish trong phạm vi hỗ trợ, nhưng không thay thế idempotent consumer cho database hoặc external side effect.

Không nhầm FIFO order với thứ tự toàn queue: ordering được tổ chức theo message group. Một group bị xử lý chậm có thể ảnh hưởng throughput của group đó.

### Kinesis Data Streams

Kinesis là streaming log theo shard. Consumer thường theo dõi sequence number và checkpoint vị trí đã xử lý. Nếu consumer commit database rồi checkpoint thất bại, record có thể được đọc lại. Nếu checkpoint trước database commit, crash có thể làm bỏ qua tác động.

Dùng event ID/sequence, inbox hoặc conditional write để chống duplicate; xử lý ordering theo shard/partition key và thiết kế reshard/rebalance phù hợp.

## 14. Google Cloud Pub/Sub

Pub/Sub có thể hoạt động với nhiều subscription/delivery mode. Cần đọc đúng semantics của subscription và client library.

### At-least-once mặc định

Trong mô hình at-least-once, message có thể được giao lại nếu subscriber không ACK đúng hạn hoặc ACK không được xác nhận theo contract. Ack deadline và lease extension quyết định thời gian subscriber giữ quyền xử lý trước khi message có thể được giao lại.

Consumer nên:

1. Nhận message.
2. Ghi inbox và business state trong transaction.
3. Commit.
4. ACK message.
5. Nếu ACK không thành công hoặc subscriber crash, redelivery được inbox nhận diện.

### Exactly-once delivery feature

Pub/Sub cung cấp tính năng exactly-once delivery cho các subscription/client mode được hỗ trợ và có điều kiện sử dụng cụ thể. Cần kiểm tra region, subscription type, client library và ACK confirmation semantics theo tài liệu hiện hành.

Ngay cả khi subscription bật exactly-once delivery:

- Nó không tự tạo transaction chung với PostgreSQL, Cloud SQL, Firestore hoặc payment API.
- Consumer vẫn có thể tự gọi một side effect nhiều lần nếu code xử lý lặp hoặc tạo operation mới.
- Publisher retry và business command idempotency vẫn cần được xem xét riêng.
- Replay, seek hoặc thao tác quản trị có thể có semantics khác với luồng delivery bình thường.

### Ordering keys

Ordering key có thể giúp giữ thứ tự message cùng key theo tính năng/configuration hỗ trợ. Ordering không đồng nghĩa exactly-once business effect; consumer vẫn cần kiểm soát duplicate, retry và version.

## 15. Spring Boot và Spring Cloud Stream: ACK semantics thuộc binder

Spring Boot có thể nhận message qua native SDK hoặc **Spring Cloud Stream**. Spring Cloud Stream giúp viết function/consumer thống nhất, nhưng settlement/ack behavior phụ thuộc **binder**, **consumer mode**, **ack configuration** và phiên bản.

Ví dụ function bean:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class OrderEventConsumerConfiguration {

    @Bean
    public Consumer<Message<OrderCreated>> orderCreated(
            OrderApplicationService orderApplicationService) {
        return message -> {
            OrderCreated event = message.getPayload();
            orderApplicationService.handle(event);
        };
    }
}
~~~

Đoạn code minh họa shape của functional consumer; binder cụ thể sẽ quyết định thời điểm settlement và cách xử lý exception.

### Những điều phải xác minh ở binder

- Khi handler return bình thường, binder ACK/complete vào thời điểm nào?
- Khi handler ném exception, binder retry nội bộ, abandon/nack hay chuyển DLQ thế nào?
- Có manual acknowledgment không? API/context nào được cung cấp?
- Binder có transaction integration với broker hoặc database không?
- Batch listener xử lý partial failure ra sao?
- Consumer concurrency, prefetch, lock renewal và max delivery có được cấu hình ở đâu?
- Retry của binder có chồng lên retry của SDK hoặc Spring Retry không?

Không giả định một cấu hình ACK dùng được cho Azure Service Bus, Kafka, RabbitMQ, SQS và Pub/Sub. Đọc tài liệu binder/version thực tế và viết integration test chứng minh thứ tự commit/ACK.

### Nguyên tắc trong handler

Handler nên gọi một application service có transaction rõ ràng:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderEventHandler {

    private final InboxRepository inbox;
    private final OrderRepository orders;

    public OrderEventHandler(
            InboxRepository inbox,
            OrderRepository orders) {
        this.inbox = inbox;
        this.orders = orders;
    }

    @Transactional
    public void handle(OrderCreated event) {
        InboxResult result = inbox.tryRecord(
                "order-projection",
                event.eventId(),
                event.payloadHash());

        if (result == InboxResult.DUPLICATE_SAME_PAYLOAD) {
            return;
        }
        if (result == InboxResult.DUPLICATE_DIFFERENT_PAYLOAD) {
            throw new MessageIdentityConflictException();
        }

        orders.applyCreatedEvent(
                event.orderId(),
                event.eventVersion());
    }
}
~~~

Đây là ví dụ minh họa: phương thức tryRecord phải dựa trên unique constraint/atomic insert, và nếu message ID trùng nhưng payload hash khác thì phải phát hiện conflict. Broker ACK chỉ diễn ra sau khi lời gọi handler hoàn tất theo settlement semantics của binder.

## 16. Business side effect bên ngoài database

Inbox bảo vệ được side effect nằm trong cùng transaction database. Nhưng nếu consumer gọi payment provider, gửi email hoặc ghi Blob, inbox transaction không thể atomic với hệ thống ngoài.

### Payment provider

Dùng provider idempotency key ổn định theo payment operation. Nếu request timeout:

- Tra cứu trạng thái bằng provider reference/key.
- Nếu đã thành công, cập nhật local state và không charge lại.
- Nếu chưa được nhận, retry với cùng key theo contract.
- Nếu trạng thái chưa rõ, giữ UNKNOWN và reconcile.

### Email/notification

Email provider có thể không hỗ trợ idempotency. Khi đó cần notification outbox, provider message reference, deduplication nội bộ hoặc chấp nhận duplicate theo business policy. Không thể tuyên bố exactly-once email chỉ vì broker delivery exactly-once.

### Blob Storage

Dùng object key ổn định theo document/event ID, conditional create/ETag, metadata chứa operation reference và kiểm tra trạng thái trước khi upload lại. Nếu ghi đè được phép, cần quy định rõ versioning và conflict handling.

### External API

Nếu API đối tác hỗ trợ idempotency key, truyền cùng key qua mọi lần retry. Nếu không hỗ trợ, cần tra cứu trạng thái, business reference hoặc quy trình đối soát. Nếu không có cách xác định kết quả, không retry side effect mù.

## 17. Poison message, retry và dead-letter queue

Một message có thể thất bại lặp đi lặp lại vì payload không hợp lệ, schema version không hỗ trợ hoặc dữ liệu tham chiếu không tồn tại.

Phân biệt:

- **Transient failure:** dịch vụ tạm thời unavailable, network reset, throttling.
- **Permanent failure:** payload sai, business rule từ chối, schema không thể xử lý.
- **Unknown outcome:** side effect có thể đã xảy ra nhưng consumer không xác định được.
- **Poison message:** message liên tục làm consumer thất bại, có thể do dữ liệu hoặc bug.

Không retry vô hạn poison message. Dùng delivery count/max attempts, backoff và DLQ theo broker. DLQ cần giữ nguyên message ID, correlation ID, schema version, failure category và thông tin chẩn đoán không nhạy cảm.

### Quy trình DLQ/replay

1. Đưa message vượt ngưỡng vào DLQ hoặc quarantine.
2. Phân loại lỗi và xác định có side effect nào đã xảy ra chưa.
3. Sửa dữ liệu/config/code hoặc tạo handler tương thích.
4. Xác minh idempotency/inbox state trước replay.
5. Replay với event ID gốc nếu cùng một sự kiện nghiệp vụ.
6. Theo dõi duplicate, thứ tự và tác động của replay.
7. Ghi audit ai đã replay, lúc nào và vì lý do gì.

Không tạo ID mới khi replay cùng một event chỉ để né deduplication. Làm vậy có thể khiến consumer coi đó là một sự kiện nghiệp vụ mới.

## 18. Ordering không đồng nghĩa exactly-once

Message có thể được giao đúng thứ tự nhưng side effect vẫn lặp; hoặc message được xử lý một lần nhưng sai thứ tự.

| Khái niệm | Câu hỏi |
| --- | --- |
| Delivery ordering | Broker giao message theo thứ tự nào? |
| Processing ordering | Consumer hoàn tất handler theo thứ tự nào? |
| Commit ordering | Database commit event theo thứ tự nào? |
| Business sequence | Event version nào hợp lệ tiếp theo? |
| Exactly-once effect | Một event có tạo đúng một tác động nghiệp vụ không? |

Nếu event OrderCreated version 1 và OrderPaid version 2 đến hai worker song song, version 2 có thể commit trước version 1. Consumer cần kiểm tra aggregate version/sequence, partition/session key hoặc serialize xử lý theo aggregate.

Có thể lưu last processed version:

~~~sql
UPDATE order_projection
SET status = 'CONFIRMED',
    last_event_version = :event_version
WHERE order_id = :order_id
  AND last_event_version = :event_version - 1;
~~~

Nếu không update được row, version đã thay đổi hoặc resource không tồn tại. Cần đọc state và quyết định merge/retry/reorder/quarantine; không tự bỏ qua mọi conflict.

## 19. Transaction boundary và các mô hình xử lý

| Mô hình | Bảo đảm | Giới hạn |
| --- | --- | --- |
| ACK trước side effect | Giảm redelivery sau ACK | Có thể mất nghiệp vụ nếu side effect thất bại |
| Side effect rồi ACK | Giảm nguy cơ mất sau khi xử lý; at-least-once | Duplicate nếu crash trước ACK |
| Inbox + DB transaction rồi ACK | Business state trong DB effectively-once theo inbox key | Không bao gồm external side effect ngoài transaction |
| Outbox + publisher retry | Không mất ý định publish khi DB commit | Publish có thể duplicate |
| Provider idempotency key | Giảm side effect trùng tại provider theo contract | Phụ thuộc provider và retention/key scope |
| Distributed transaction/transactional messaging | Có thể atomic trong phạm vi participant hỗ trợ | Không phổ quát; tăng coupling/operational complexity |
| Saga + compensation | Quản lý nhiều bước phân tán | Compensation không phải rollback tức thời và có thể thất bại |

Không nên chọn distributed transaction chỉ để tránh viết inbox/outbox. Đánh giá số participant, broker/database support, failure recovery, latency và vận hành. Với nhiều managed service khác provider, outbox/inbox và saga thường dễ áp dụng hơn.

## 20. Observability: đo delivery và business effect riêng

Metrics cần tách hai lớp:

| Metric | Cho biết |
| --- | --- |
| publish_attempts_total | Số lần producer gửi publish |
| broker_publish_confirmed_total | Số publish được xác nhận |
| delivery_attempts_total | Số lần consumer nhận/giao |
| handler_started_total | Số lần handler bắt đầu |
| handler_succeeded_total | Số lần handler hoàn tất |
| business_effect_committed_total | Số transaction/business effect commit |
| inbox_duplicate_total | Số lần phát hiện message đã xử lý |
| ack_failed_total | Số ACK/Complete/checkpoint thất bại |
| redelivery_total | Số lần broker giao lại |
| dead_letter_total | Số message vào DLQ |
| unknown_outcome_total | Số side effect cần reconcile |
| replay_total | Số message được replay |
| processing_lag_seconds | Độ trễ xử lý từ publish tới commit |

Không lấy số message delivered làm số business transaction thành công. Một message có thể được giao nhiều lần nhưng chỉ một business effect commit. Ngược lại, broker ACK thành công không chứng minh external payment/email đã thành công.

### Log và trace

Ghi các trường có kiểm soát:

- Event ID/message ID.
- Consumer name và subscription/queue.
- Delivery count/attempt number.
- Aggregate ID và event version nếu được phép.
- Processing duration, commit outcome và ACK outcome.
- Error category, retry delay và DLQ reason.

Không log payload chứa dữ liệu cá nhân, token, secret, connection string hoặc payment data nhạy cảm. Tránh dùng event ID làm metric label cardinality cao.

## 21. Kiểm thử bảo đảm giao nhận và tác động nghiệp vụ

Một test chỉ xác nhận consumer nhận được message chưa đủ. Cần kiểm tra crash window và trạng thái cuối.

### Test matrix

| Kịch bản | Delivery mong đợi | Business effect mong đợi |
| --- | --- | --- |
| Handler thành công, ACK thành công | Một lần giao thường | Một commit |
| Crash trước transaction | Redelivery | Một commit sau retry |
| Crash sau DB commit, trước ACK | Redelivery | Inbox ngăn commit nghiệp vụ lần hai |
| ACK trước commit rồi crash | Không redelivery theo mode đã ACK | Test phải phát hiện nguy cơ mất business effect |
| ACK response bị mất | Có thể redelivery tùy broker | Không lặp side effect |
| Broker publish accepted, producer mất confirmation | Producer có thể publish lại | Consumer dedupe cùng event ID |
| Payment provider thành công, response mất | Message/request có thể retry | Cùng provider idempotency key, một payment |
| Poison message | Retry giới hạn rồi DLQ | Không tạo side effect một phần ngoài policy |
| Replay DLQ | Message được giao lại theo quy trình | Không tạo nghiệp vụ trùng |
| Event sai thứ tự | Có thể được giao theo partition/session contract | Version check ngăn state regression |

### Failure injection

1. Kill consumer sau khi database commit nhưng trước ACK.
2. Ngắt kết nối ngay sau khi broker nhận publish.
3. Làm ACK/Complete timeout.
4. Làm external API trả timeout sau khi đã xử lý request.
5. Cho lock/visibility/ack deadline hết hạn trong lúc handler chạy.
6. Khởi chạy hai consumer cùng nhận/claim một operation.
7. Replay message cũ sau khi inbox retention gần hết hạn.
8. Gửi cùng message ID nhưng payload khác để xác minh conflict.
9. Gửi event version sai thứ tự.
10. Kiểm tra DLQ và replay có giữ event ID gốc.

### Test trên dịch vụ thật

- Dùng Azure Service Bus/Storage, AWS SQS hoặc Google Pub/Sub trong môi trường dev/test riêng.
- Chạy đúng client library/binder và cấu hình settlement đang dùng.
- Đếm delivery count, ACK/complete và business commits.
- Kiểm tra broker feature exactly-once/duplicate detection trong phạm vi được hỗ trợ.
- Xác minh database/inbox/outbox bằng query trạng thái cuối.
- Không tạo failure injection gây mất dữ liệu trên queue/topic production.

## 22. Bài thực hành: xây dựng consumer effectively-once

**Bối cảnh:** Spring Boot nhận event OrderPaid từ một broker managed. Consumer cần cập nhật order, ghi ledger và phát OrderReceiptRequested. Broker có thể giao lại message; ACK có thể thất bại sau khi database commit.

### Phần A — Xác định contract

1. Ghi rõ broker và delivery model.
2. Xác định MessageId/EventId, subscription/queue và retention.
3. Xác định ACK/Complete/checkpoint được thực hiện bởi SDK hay binder.
4. Ghi rõ message lock/visibility/ack deadline hoặc checkpoint semantics.
5. Định nghĩa business invariant: một event OrderPaid chỉ tạo một ledger entry cho một payment reference.

### Phần B — Thiết kế transaction consumer

1. Tạo bảng inbox với unique key (consumer_name, event_id).
2. Trong một transaction, insert inbox và cập nhật order/ledger.
3. Nếu inbox duplicate và payload hash khớp, không lặp business effect.
4. Nếu event ID trùng nhưng payload hash khác, đưa vào xử lý lỗi/điều tra.
5. Commit trước ACK/Complete.
6. Xác minh transaction rollback sẽ rollback cả inbox và business state.

### Phần C — Phát sự kiện tiếp theo

1. Ghi OrderReceiptRequested vào outbox trong cùng transaction với business update.
2. Publisher gửi event với ID ổn định.
3. Nếu publish confirmation không rõ, publisher retry cùng ID.
4. Consumer tiếp theo dùng inbox hoặc idempotency key tương ứng.
5. Nếu email provider không hỗ trợ idempotency, ghi rõ giới hạn và cách reconciliation.

### Phần D — Kiểm thử

1. Gửi cùng event ba lần; chỉ một ledger entry được tạo.
2. Crash sau commit trước ACK; redelivery không lặp ledger.
3. Làm outbox publisher mất ACK; event có thể gửi lại nhưng consumer chống trùng.
4. Gửi cùng ID với payload khác; phải phát hiện conflict.
5. Replay DLQ; giữ event identity và audit.
6. Làm payment/email API timeout sau side effect; kiểm tra unknown outcome và reconciliation.

### Sản phẩm cần nộp

- Bảng phân biệt delivery guarantee và business-effect guarantee.
- Sơ đồ publish, delivery, commit, side effect và ACK.
- Schema inbox/outbox cùng unique constraints.
- Bằng chứng test crash sau commit trước ACK.
- Bằng chứng duplicate delivery không tạo business effect thứ hai.
- Chính sách unknown outcome, DLQ, replay và retention.
- Metrics riêng cho delivery attempts, ACK và business commits.

### Câu hỏi tự kiểm tra

1. At-least-once delivery khác exactly-once business effect ở điểm nào?
2. Vì sao ACK trước commit có thể làm mất nghiệp vụ?
3. Vì sao commit trước ACK có thể dẫn tới duplicate delivery?
4. Inbox cần nằm trong transaction nào để bảo vệ business state?
5. Outbox giải quyết khoảng trống nào giữa database và broker?
6. Exactly-once delivery của một subscription có bao gồm payment API mà consumer gọi không?
7. Vì sao Event Hubs checkpoint phải được lưu sau business commit?
8. Service Bus Peek-Lock khác Receive-and-Delete thế nào?
9. SQS FIFO deduplication và consumer inbox bảo vệ các phạm vi nào?
10. Pub/Sub exactly-once delivery không thay thế điều gì ở tầng ứng dụng?
11. Vì sao event ID phải ổn định qua publisher retry và DLQ replay?
12. Làm sao phân biệt message delivered nhiều lần với business effect commit nhiều lần?

## 23. Ghi nhớ

- **Delivery guarantee** mô tả broker giao message; **business-effect guarantee** mô tả trạng thái và side effect thực tế của ứng dụng.
- At-most-once có thể mất message; at-least-once có thể giao trùng; exactly-once chỉ có ý nghĩa trong phạm vi dịch vụ/transaction được định nghĩa.
- Với consumer cập nhật database, thường commit inbox + business state trước rồi ACK. Nếu ACK thất bại, redelivery được inbox nhận diện.
- Outbox bảo vệ ý định publish cùng transaction database; publisher vẫn có thể gửi trùng nếu confirmation bị mất.
- Exactly-once delivery không tự bao gồm payment, email, Blob, database hoặc API ngoài broker.
- Effectively-once đạt được bằng event identity ổn định, unique constraint, inbox/outbox, provider idempotency key, state machine và reconciliation.
- Service Bus lock, Event Hubs checkpoint, SQS visibility timeout và Pub/Sub ack deadline có semantics khác nhau; kiểm tra đúng binder/client version.
- DLQ/replay phải giữ event identity và kiểm tra side effect trước khi phát lại.
- Đo delivery attempts, handler runs, business commits, ACK failures, duplicates và unknown outcomes thành các chỉ số riêng.

## Tài liệu tham khảo

- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Service Bus duplicate detection](https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection)
- [Azure Event Hubs checkpoints and consumer groups](https://learn.microsoft.com/azure/event-hubs/event-hubs-features)
- [AWS SQS Standard queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues.html)
- [Amazon SQS FIFO queues and exactly-once processing](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Amazon Kinesis Data Streams consumers](https://docs.aws.amazon.com/streams/latest/dev/building-consumers.html)
- [Google Cloud Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Google Cloud Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Transactional outbox pattern](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
