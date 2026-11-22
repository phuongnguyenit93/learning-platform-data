# Cho rằng chuyển sang bất đồng bộ sẽ tự giải quyết tính nhất quán

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Sai lầm thiết kế.
>
> **Thông điệp:** Chuyển một lời gọi đồng bộ thành message hoặc event có thể giảm sự phụ thuộc về thời gian giữa producer và consumer, hấp thụ tải và giúp các thành phần tiếp tục hoạt động khi một consumer tạm thời gián đoạn. Nhưng **bất đồng bộ không tự làm dữ liệu nhất quán, không loại bỏ race condition, không bảo đảm đúng thứ tự, không ngăn duplicate và không biến nhiều database thành một transaction nguyên tử**. Nó thay đổi cách hệ thống phối hợp; vì vậy phải thiết kế rõ semantics, trạng thái trung gian, delivery guarantees, idempotency, ordering, reconciliation và trải nghiệm người dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt synchronous request/response, asynchronous command, domain event, message queue, event stream và background job.
2. Giải thích vì sao asynchronous communication thường tạo hoặc làm lộ ra eventual consistency, nhưng không tự bảo đảm tính nhất quán nghiệp vụ.
3. Phân biệt consistency, atomicity, isolation, durability, ordering, delivery semantics và freshness.
4. Nhận diện duplicate delivery, out-of-order events, lost updates, stale reads, concurrent writes và partial failures.
5. Thiết kế consumer idempotent và version-aware để xử lý message lặp hoặc đến trễ.
6. Sử dụng transactional outbox/inbox để giảm lỗi giữa commit database và publish/consume event.
7. Chọn partition key, aggregate version, sequence và concurrency control theo business invariant.
8. Thiết kế saga/orchestration/choreography và compensating actions cho workflow nhiều service.
9. Định nghĩa read-your-writes, monotonic reads, freshness SLO và trạng thái PENDING/UNKNOWN/COMPLETED cho sản phẩm.
10. Biết khi nào cần request/response, khi nào event/queue phù hợp và khi nào nên kết hợp cả hai.
11. Kiểm chứng bằng fault injection, replay, concurrency tests, reconciliation và telemetry.
12. Tránh các tuyên bố thiếu chính xác như “Kafka bảo đảm exactly-once cho toàn bộ hệ thống” hoặc “event đã được publish nghĩa là mọi service đã cập nhật”.

Các đoạn mã, thời gian, ngưỡng và số liệu trong bài là ví dụ. Delivery semantics thực tế phải dựa trên broker, database, connector, cấu hình và cách ứng dụng sử dụng chúng.

## 2. Sai lầm: dùng message queue là dữ liệu sẽ tự nhất quán

Xét luồng đặt hàng:

~~~text
Order Service
   │
   ├── ghi Order DB
   │
   └── publish OrderCreated
              │
              ▼
           Broker
              │
              ▼
       Inventory Consumer
              │
              ▼
         Inventory DB
~~~

Đội phát triển thay lời gọi HTTP trực tiếp từ Order sang Inventory bằng event OrderCreated. Order API trả về nhanh hơn, producer không phải đợi Inventory và broker có thể giữ message khi consumer offline.

Nhưng nhiều câu hỏi mới xuất hiện:

- Order DB commit thành công nhưng publish event thất bại thì sao?
- Broker gửi event hai lần thì Inventory có reserve hàng hai lần không?
- Event của Order version 8 đến sau version 9 thì consumer xử lý thế nào?
- Inventory xử lý xong nhưng crash trước khi ack thì sao?
- Order đã báo thành công cho người dùng nhưng reservation chưa hoàn tất thì UI hiển thị gì?
- Hai checkout đồng thời cùng mua SKU cuối cùng thì ai quyết định còn hàng?
- Consumer lag 20 phút, dữ liệu tồn kho trên màn hình có được coi là hiện tại không?
- Một event bị đưa vào dead-letter queue thì workflow có tự hoàn thành không?

**Bất đồng bộ giải quyết một phần coupling về thời gian.** Nó không tự trả lời những câu hỏi về tính đúng đắn và trạng thái nghiệp vụ.

## 3. Phân biệt các khái niệm dễ bị trộn lẫn

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Synchronous | Caller chờ response trong cùng interaction | Order gọi Payment API |
| Asynchronous | Caller gửi công việc/message và tiếp tục; kết quả đến sau hoặc được truy vấn | Order phát OrderCreated |
| Atomicity | Một nhóm thay đổi cùng thành công hoặc cùng thất bại trong transaction boundary | Update Order + insert Outbox |
| Consistency | Trạng thái trước/sau tuân thủ invariants và rules đã định nghĩa | Không bán vượt tồn kho |
| Isolation | Các thao tác đồng thời không tạo trạng thái sai theo isolation rules | Hai checkout tranh SKU cuối |
| Durability | Commit được giữ theo guarantees của storage | DB transaction đã commit |
| Delivery guarantee | Broker/consumer có thể nhận và xử lý message theo semantics nào | At-least-once |
| Ordering | Những message nào được bảo đảm thứ tự và trong phạm vi nào | Theo partition/key |
| Idempotency | Lặp cùng một operation không tạo thêm tác động nghiệp vụ | Cùng payment idempotency key |
| Freshness | Dữ liệu bản sao mới đến đâu so với nguồn | Projection trễ 3 giây |
| Reconciliation | Đối chiếu và sửa sai lệch theo authoritative source | So khớp Payment với Order |

Một hệ thống có thể truyền message đúng một lần theo một phạm vi kỹ thuật mà vẫn có business data sai. Ngược lại, một hệ thống nhận message nhiều lần vẫn có thể giữ kết quả nghiệp vụ đúng nếu consumer idempotent.

## 4. Synchronous cũng không tự bảo đảm consistency

Một hiểu nhầm khác là đồng bộ luôn nhất quán còn bất đồng bộ mới gây eventual consistency.

Ví dụ:

~~~text
Order ──HTTP──► Payment
   │                │
   │                └── Payment DB commit
   │
   └── timeout trước khi nhận response
~~~

Payment có thể đã authorize thành công nhưng response bị mất trên mạng. Order không biết giao dịch đã thành công hay chưa. Nếu retry không có idempotency, có thể tạo authorization thứ hai.

HTTP response thành công cũng không bảo đảm Order DB và Payment DB cùng commit nguyên tử. Nếu Payment trả 200 rồi Order crash trước khi lưu trạng thái, hai hệ thống vẫn lệch.

**Synchronous giúp caller nhận phản hồi ngay**, nhưng không tạo distributed transaction hoặc atomic commit qua nhiều service. Tính đúng đắn phụ thuộc vào transaction boundary, idempotency, state machine và recovery.

## 5. Eventual consistency thực sự có nghĩa gì?

**Eventual consistency** là mô hình trong đó các bản sao có thể tạm thời khác nhau sau một thay đổi, nhưng nếu không có thay đổi mới và quá trình truyền/áp dụng tiếp tục thành công, chúng sẽ hội tụ về trạng thái phù hợp.

Ví dụ:

~~~text
t0: Customer DB: email = old@example.test
t1: Customer đổi email thành new@example.test
t2: Event được publish
t3: Notification nhận event
t4: Notification projection cập nhật email mới
~~~

Trong khoảng t1–t4:

- Customer API trả email mới.
- Notification projection có thể vẫn chứa email cũ.
- Search hoặc Analytics có thể cập nhật ở thời điểm khác.

Đây có thể là trạng thái được thiết kế chấp nhận nếu consumer biết dữ liệu có thể stale và hành vi nghiệp vụ phù hợp.

### 5.1. Eventually cần điều kiện và giới hạn

Không thể chỉ nói “rồi dữ liệu sẽ nhất quán”. Phải xác định:

- Producer có phát event bền vững không?
- Broker có giữ message đủ lâu không?
- Consumer có hoạt động trở lại không?
- Poison message có bị mắc ở retry/DLQ không?
- Schema có còn tương thích không?
- Consumer có áp dụng event thành công không?
- Có event bị bỏ qua do offset/checkpoint sai không?
- Có ai tiếp tục ghi đè bằng nguồn cũ không?
- Có quy trình replay/reconciliation không?

Nếu một message bị dead-letter vĩnh viễn và không có người xử lý, dữ liệu **không tự hội tụ**.

### 5.2. Định nghĩa convergence theo nghiệp vụ

Không phải mọi bản sao phải có byte giống nhau. Order snapshot giá tại thời điểm checkout khác Catalog price hiện tại là hợp lệ. Customer projection có thể chỉ chứa contact reference, trong khi nguồn có đầy đủ profile.

Hội tụ có nghĩa các bản sao phản ánh đúng semantics, version và freshness đã thỏa thuận.

## 6. Message broker bảo đảm điều gì?

Broker thường cung cấp các cơ chế:

- Buffer message khi consumer chậm hoặc tạm offline.
- Acknowledgement/offset.
- Retry hoặc redelivery theo cấu hình.
- Persistence/replication theo durability settings.
- Partitioning và ordering trong phạm vi nhất định.
- Consumer groups hoặc subscriptions.
- Dead-letter handling tùy sản phẩm/cấu hình.
- Retention/replay với event streaming.

Broker không tự bảo đảm:

- Producer đã commit database cùng với publish.
- Consumer xử lý business logic thành công.
- Consumer không tạo duplicate side effects.
- Nhiều database commit nguyên tử.
- Events luôn đến đúng thứ tự toàn cục.
- Consumer áp dụng event mới nhất.
- Projection phản ánh đúng nghiệp vụ.
- Mọi message được xử lý trong deadline mong muốn.

### 6.1. Acknowledgement khác business completion

Consumer có thể ack sau khi lưu một message vào local processing queue, nhưng business action còn chưa hoàn tất. Cần quy định ack tại boundary nào và trạng thái nào được coi là processed.

### 6.2. Producer confirmation khác consumer completion

Publisher confirm cho biết broker đã nhận/persist message theo guarantee của broker. Nó không nói Notification, Inventory hoặc Analytics đã xử lý xong.

### 6.3. Broker durability cần cấu hình đúng

Replication factor, acknowledgements, persistence, quorum, retention, disk capacity và failure recovery đều ảnh hưởng. Không thể nói “đã dùng Kafka/RabbitMQ nên message không mất” mà bỏ qua cấu hình và failure modes.

## 7. Delivery semantics: at-most-once, at-least-once và exactly-once

### 7.1. At-most-once

Message có thể được xử lý không quá một lần, nhưng có thể mất nếu failure xảy ra ở một số thời điểm.

Ưu điểm: tránh duplicate theo semantics đã chọn. Nhược điểm: có thể bỏ lỡ công việc.

Phù hợp với một số telemetry/notification không critical hoặc dữ liệu có thể tái tạo, nếu business chấp nhận loss.

### 7.2. At-least-once

Message được retry/redeliver cho tới khi được xác nhận theo policy, nhưng consumer có thể nhận nhiều lần.

Ưu điểm: giảm nguy cơ mất message khi lỗi tạm thời. Nhược điểm: cần idempotency/dedup.

Đây là mô hình thường gặp trong hệ thống phân tán thực tế.

### 7.3. Exactly-once

“Exactly-once” chỉ có ý nghĩa khi nói rõ **phạm vi**: broker processing, transactional consume-produce trong một hệ sinh thái, hay business side effect xuyên database/provider.

Ví dụ một broker có transaction semantics cho consume và produce trong cùng hệ thống không tự làm cho lệnh trừ tiền ở external provider chỉ chạy đúng một lần. Cần idempotency key và contract phía provider.

### 7.4. Bảng so sánh

| Guarantee | Có thể mất message? | Có thể duplicate? | Yêu cầu consumer |
| --- | --- | --- | --- |
| At-most-once | Có, tùy failure window | Theo semantics không redeliver | Chấp nhận loss hoặc có nguồn tái tạo |
| At-least-once | Giảm nguy cơ mất qua retry, tùy retention/config | Có | Idempotency/dedup |
| Exactly-once trong phạm vi broker | Theo transaction/durability guarantees cụ thể | Có thể không lặp trong phạm vi đó | Tuân thủ transaction/offset protocol |
| Business exactly-once end-to-end | Không thể mặc định suy ra từ broker | Không thể mặc định suy ra | Domain idempotency, durable state, reconciliation |

## 8. Duplicate delivery và idempotency

Một tình huống phổ biến:

~~~text
1. Consumer nhận PaymentAuthorized
2. Consumer cập nhật Order DB thành PAID
3. Consumer crash trước khi ack
4. Broker gửi lại PaymentAuthorized
5. Consumer xử lý lần nữa
~~~

Nếu lần xử lý thứ hai gửi thêm email, tạo thêm invoice hoặc trừ thêm tồn kho, hệ thống có duplicate side effect.

### 8.1. Idempotent operation

Một operation idempotent có kết quả nghiệp vụ tương đương khi được thực hiện lặp với cùng identity/input theo contract.

Ví dụ:

- setOrderPaymentState(PAID, paymentId) có thể idempotent nếu kiểm tra version và payment reference.
- incrementStockReservedBy(1) không idempotent nếu thực hiện lại.
- reserve(orderId, sku, qty) có thể idempotent nếu owner enforce unique reservation key.

### 8.2. Dùng event ID để deduplicate

Ví dụ bảng inbox:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    message_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Consumer lưu message ID đã xử lý. Unique constraint giúp hai worker đồng thời không cùng ghi nhận một message như mới, nhưng **dedup record và business update phải được commit nguyên tử**.

### 8.3. Transaction local cho dedup và side effect

~~~text
BEGIN
  INSERT processed_messages(consumer, message_id)
    -- unique key rejects duplicate
  UPDATE order_projection ...
  INSERT notification_outbox ...
COMMIT
ACK message
~~~

Nếu transaction rollback, message có thể được redelivered và xử lý lại. Nếu transaction commit nhưng ack thất bại, lần nhận tiếp theo bị dedup. Outbox tách việc gửi side effect ra khỏi local transaction.

### 8.4. Dedup retention

Không xóa processed-message records quá sớm nếu broker có thể replay message cũ. Retention phải liên quan tới message retention, replay windows, business idempotency và chi phí storage.

### 8.5. Idempotency key tại domain owner

Với Payment API, caller gửi idempotency key ổn định cho một business attempt. Payment Service lưu key và kết quả; retry cùng key trả lại kết quả đã có thay vì tạo giao dịch mới.

Key phải có scope, retention và conflict semantics rõ. Không tạo key mới mỗi lần retry.

## 9. Ordering: message đến sau chưa chắc mới hơn

Giả sử một Customer thay đổi trạng thái:

~~~text
Version 7: email = old@example.test
Version 8: email = new@example.test
Version 9: emailVerified = true
~~~

Consumer nhận theo thứ tự 9, 8, 7 vì retry hoặc nhiều partitions. Nếu áp dụng mù, projection có thể quay lại email cũ.

### 9.1. Không có global ordering mặc định

Broker thường chỉ cung cấp ordering trong một phạm vi cụ thể như partition hoặc queue, phụ thuộc cấu hình và consumer concurrency. Nhiều partitions có thể xử lý song song và không có một thứ tự toàn cục giữa tất cả keys.

### 9.2. Partition key

Nếu cần thứ tự cho một aggregate, thường dùng aggregate ID làm key để các event của cùng aggregate đi vào cùng partition (tùy broker). Điều này vẫn cần kiểm tra producer concurrency, retries và consumer processing order.

### 9.3. Aggregate version

Event mang version tăng dần:

~~~json
{
  "eventId": "evt-9002",
  "aggregateId": "customer-123",
  "aggregateVersion": 9,
  "eventType": "CustomerVerificationChanged"
}
~~~

Consumer có thể:

- Áp dụng nếu version lớn hơn version hiện tại và semantics cho phép.
- Bỏ qua duplicate/cũ.
- Buffer hoặc retry nếu thiếu version trước đó mà business cần đầy đủ transition.
- Gọi owner API hoặc rebuild projection khi phát hiện gap.

Không phải mọi projection đều cần xử lý tất cả transition; một số chỉ cần latest state. Nhưng điều đó phải là quyết định rõ.

### 9.4. Version không thay thế concurrency control

Hai command cùng đọc version 7 và cùng ghi version 8 có thể race. Owner cần optimistic locking, compare-and-set, serializable transaction hoặc cơ chế khóa phù hợp.

## 10. Lost update và concurrent writes

Hai consumer xử lý cùng một entity:

~~~text
Consumer A đọc balance = 100
Consumer B đọc balance = 100
Consumer A ghi balance = 90
Consumer B ghi balance = 80
~~~

Nếu B tính dựa trên dữ liệu cũ, cập nhật của A có thể bị ghi đè. Bất đồng bộ có thể làm concurrency tăng vì nhiều message được xử lý song song.

### 10.1. Optimistic concurrency

Dùng version:

~~~sql
UPDATE accounts
SET balance = :new_balance,
    version = version + 1
WHERE account_id = :id
  AND version = :expected_version;
~~~

Nếu số rows updated bằng 0, dữ liệu đã đổi; cần đọc lại và áp dụng lại business rule hoặc từ chối command.

### 10.2. Pessimistic locking

Có thể khóa row/aggregate trong transaction ngắn khi invariant cần tuần tự hóa. Cần tránh giữ lock trong khi gọi remote service hoặc chờ message vì có thể tạo contention/deadlock.

### 10.3. Atomic conditional update

Một số invariant có thể enforce trong DB:

~~~sql
UPDATE inventory
SET available = available - :qty
WHERE sku = :sku
  AND available >= :qty;
~~~

Kiểm tra row count để biết reservation thành công. DB transaction là nơi quyết định authoritative quantity; event chỉ thông báo kết quả sau commit.

### 10.4. Serialize theo aggregate

Một partition/queue per key hoặc actor-like processing có thể tuần tự hóa updates cho cùng aggregate. Cần cân bằng throughput và hot keys; partitioning không thay business validation.

## 11. Transactional outbox: không để DB commit và publish rời nhau

Lỗi kinh điển:

~~~text
Application:
  1. UPDATE orders
  2. COMMIT DB
  3. Publish OrderConfirmed
~~~

Nếu bước 2 thành công nhưng bước 3 lỗi, database có trạng thái mới mà consumers không biết. Nếu publish trước rồi DB rollback, consumers thấy event cho thay đổi chưa từng commit.

### 11.1. Outbox pattern

Trong cùng một local DB transaction:

~~~text
BEGIN
  UPDATE orders SET status = 'CONFIRMED'
  INSERT INTO outbox(event_id, aggregate_id, type, payload)
COMMIT
~~~

Sau đó một publisher đọc outbox và gửi message:

~~~text
Order DB + Outbox
       │
       ▼
Outbox Publisher
       │
       ▼
Broker
       │
       ▼
Consumers
~~~

### 11.2. Điều outbox giải quyết

- Business state và intent-to-publish được commit nguyên tử trong một database.
- Nếu publisher offline, outbox vẫn còn để gửi sau.
- Có thể retry publish.
- Có audit/recovery path cho event chưa gửi.

### 11.3. Điều outbox không giải quyết

- Publisher có thể gửi trùng nếu crash sau send trước khi đánh dấu published.
- Consumer có thể lỗi hoặc xử lý sai event.
- Broker/consumer ordering không tự được giải quyết.
- Nhiều databases vẫn không có một transaction chung.
- Event payload vẫn có thể sai semantics.

Consumer cần idempotency; outbox cần monitoring backlog, retry và retention.

### 11.4. Outbox publisher

Publisher có thể poll theo batch hoặc dùng CDC. Nếu nhiều publisher cùng đọc outbox, cần claim/locking hoặc cơ chế lease phù hợp. Không giữ transaction/row lock quá lâu khi gửi mạng.

### 11.5. Outbox cleanup

Chỉ xóa/archival event sau khi policy đảm bảo đã publish và retention/replay requirements được đáp ứng. Cần xử lý event poison và publisher offset.

## 12. Inbox pattern: làm rõ ranh giới xử lý message

Consumer inbox lưu message IDs đã nhận/áp dụng trong local transaction.

~~~text
Broker
  │
  ▼
Consumer
  │
  ▼
BEGIN
  ├── insert inbox record
  ├── validate aggregate version
  ├── update local projection/state
  └── write local outbox if needed
COMMIT
  │
  ▼
ACK
~~~

Inbox giúp deduplicate message và kết hợp việc ghi nhận đã xử lý với thay đổi local. Nếu consumer gọi external provider, side effect đó vẫn không nằm trong local DB transaction; cần idempotency key hoặc outbox + provider contract.

### 12.1. Inbox không thay thế business idempotency

Hai event ID khác nhau có thể đại diện cùng một business action. Ví dụ producer phát lại cùng ý nghĩa dưới một event ID mới. Cần domain key/idempotency key theo operation, không chỉ message ID.

## 13. Saga: transaction nhiều service không tự trở thành atomic

Ví dụ checkout cần Order, Inventory và Payment:

~~~text
Order: create PENDING
   │
   ▼
Inventory: reserve
   │
   ▼
Payment: authorize
   │
   ▼
Order: confirm
~~~

Mỗi service commit transaction cục bộ. Trong thời gian workflow, trạng thái trung gian là bình thường. Nếu một bước thất bại, saga thực hiện hành động bù trừ hoặc chuyển sang trạng thái cần xử lý.

### 13.1. Compensation

Nếu Payment bị decline sau khi Inventory reserve:

- Inventory release reservation.
- Order chuyển PAYMENT_FAILED hoặc CANCELLED.
- Notification gửi thông tin phù hợp.

Nếu Payment timeout và kết quả không rõ, không release stock hoặc tạo payment mới ngay một cách mù quáng. Trước tiên cần query/reconcile Payment bằng idempotency key.

### 13.2. Compensation không phải rollback database

Rollback local transaction chỉ áp dụng trước khi transaction commit. Compensation là một hành động nghiệp vụ mới, có thể thất bại và cần retry.

Ví dụ refund là một giao dịch mới; nó không xóa được lịch sử capture.

### 13.3. Orchestration

Một coordinator lưu workflow state, gửi commands và xử lý responses/timeouts. Ưu điểm là trạng thái process dễ nhìn và policy tập trung. Rủi ro là coordinator có thể thành bottleneck hoặc chứa quá nhiều domain logic.

### 13.4. Choreography

Các service phát và tiêu thụ domain events. Ưu điểm là producer ít biết consumers. Rủi ro là workflow phân tán, khó theo dõi event cycles và điều tra trạng thái bị kẹt.

### 13.5. Saga cần durable state

Một saga dài phải lưu:

- Saga ID và business correlation.
- Current step/state.
- Command/event IDs.
- Deadline/timeout.
- Retry count.
- Compensation state.
- Last error và owner.
- Manual intervention status.

Không giữ toàn bộ workflow chỉ trong memory của một process.

## 14. Trạng thái UNKNOWN và timeout

Một request timeout không chứng minh thao tác thất bại. Ví dụ Payment provider đã xử lý nhưng response bị mất.

Một state machine thực dụng:

~~~text
CREATED
   │
   ▼
SUBMITTED
   │
   ├── approved ──► SUCCEEDED
   ├── declined ──► FAILED
   └── timeout ───► UNKNOWN
                       │
                       ├── reconcile approved ─► SUCCEEDED
                       ├── reconcile declined ─► FAILED
                       └── still unknown ───────► PENDING_REVIEW
~~~

### 14.1. Không biến UNKNOWN thành FAILED quá sớm

Nếu Order đánh dấu payment failed rồi retry với key mới, có thể charge hai lần. Giữ state UNKNOWN/PENDING cho tới khi có bằng chứng hoặc deadline/policy quyết định.

### 14.2. Query status

Owner service có endpoint/operation tra cứu theo idempotency key hoặc payment reference. Đây là cách giải quyết ambiguity sau timeout, không cần giả định caller luôn nhận được response đầu tiên.

### 14.3. Reconciliation job

Một job có thể đối chiếu Payment Service với provider settlement/status APIs, tìm giao dịch UNKNOWN quá lâu và cập nhật state theo owner contract. Job phải idempotent, audit và có alert khi không thể reconcile.

## 15. Read-your-writes và trải nghiệm người dùng

Sau khi người dùng đổi profile, họ refresh trang nhưng projection chưa cập nhật. Người dùng thấy dữ liệu cũ và nghĩ thao tác thất bại.

Cần xác định consistency expectation:

### 15.1. Read-your-writes

Sau khi một user ghi thành công, lần đọc tiếp theo trong cùng session có thể được bảo đảm nhìn thấy thay đổi vừa ghi. Có thể thực hiện bằng cách:

- Trả authoritative result từ owner trong response.
- Trả version/ETag và query projection tới version tối thiểu.
- Đọc trực tiếp owner trong khoảng ngắn.
- Cập nhật local UI optimistically với trạng thái pending rõ.

### 15.2. Monotonic reads

Người dùng không nên thấy version mới rồi sau đó lại thấy version cũ do request được route tới replicas/projections khác nhau. Version tokens hoặc session consistency có thể giúp.

### 15.3. Eventual consistency có UX rõ

Ví dụ:

- “Đơn hàng đã được tạo, đang chờ xác nhận thanh toán.”
- “Yêu cầu cập nhật đang được xử lý.”
- “Thông tin có thể mất tối đa vài giây để xuất hiện trong báo cáo.”
- “Thanh toán đang được xác minh; vui lòng không gửi lại giao dịch.”

Không báo “thành công hoàn toàn” khi chỉ mới enqueue message nếu business operation chưa hoàn thành.

### 15.4. Optimistic UI

UI có thể hiển thị trạng thái tạm thời trước khi backend workflow hoàn tất. Phải có cơ chế reconcile, rollback visual state hoặc thông báo thất bại. Optimistic UI không thay transaction guarantees.

## 16. Định nghĩa consistency/freshness SLO

Không nên để “eventually” không có deadline.

Ví dụ cho Customer projection:

> 99% CustomerUpdated events được áp dụng vào Notification projection trong vòng 30 giây; 99,9% trong vòng 5 phút.

Đây là ví dụ mục tiêu; phải chọn theo nhu cầu sản phẩm.

### 16.1. Các chỉ số hữu ích

- Event publish latency.
- Broker enqueue-to-consume lag.
- Oldest message age.
- Consumer processing duration.
- Retry/DLQ rate.
- Projection applied version.
- Source-to-projection freshness.
- Reconciliation mismatch count/age.
- Workflow completion time.
- UNKNOWN/PENDING state age.

### 16.2. Đo đúng boundary

Nếu broker lag thấp nhưng consumer áp dụng projection chậm do DB locks, chỉ đo broker lag sẽ bỏ sót. Đo từ source event occurred/committed time tới thời điểm projection được apply.

### 16.3. Không dùng average để che tail

P50 lag 1 giây có thể đi cùng P99 lag 30 phút. SLO cần percentile hoặc tỷ lệ records hoàn thành trong deadline, tùy semantics.

### 16.4. Freshness khác correctness

Projection có thể cập nhật trong 1 giây nhưng sai mapping. Cần quality checks/reconciliation để đo correctness riêng.

## 17. Event schema và semantic versioning

Consumer không thể xử lý đúng nếu event không nói rõ semantics.

Ví dụ:

~~~json
{
  "eventId": "evt-123",
  "eventType": "InventoryReserved",
  "schemaVersion": 2,
  "aggregateId": "reservation-456",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-12T03:20:00Z",
  "correlationId": "checkout-789",
  "data": {
    "orderId": "order-100",
    "sku": "SKU-1",
    "quantity": 2,
    "reservationStatus": "CONFIRMED"
  }
}
~~~

### 17.1. Phân biệt event facts và commands

- **Command:** yêu cầu điều gì đó xảy ra, ví dụ ReserveInventory.
- **Event:** thông báo điều gì đã xảy ra, ví dụ InventoryReserved.

Command có thể bị từ chối. Event nên phản ánh fact đã commit theo semantics owner. Đặt tên lẫn lộn dễ khiến consumer giả định một yêu cầu đã thành công.

### 17.2. Event payload tối thiểu

Chỉ gửi field cần cho consumer. Tránh raw PII/secrets hoặc toàn bộ aggregate nếu không cần. Reference ID có thể được dùng để consumer truy vấn owner API với quyền phù hợp.

### 17.3. Schema compatibility

Thêm optional field không phải lúc nào cũng safe với strict consumers. Enum mới có thể làm parser lỗi. Đổi đơn vị hoặc ý nghĩa field có thể gây sai dữ liệu mà không có exception.

Cần schema registry/contract tests, compatibility mode, deprecation window và kế hoạch xử lý replay events cũ.

### 17.4. Event identity khác aggregate identity

- eventId: nhận diện một message/fact cụ thể.
- aggregateId: nhận diện entity/aggregate.
- aggregateVersion: thứ tự state của aggregate.
- correlationId: nối các bước trong workflow.
- causationId: chỉ ra command/event gây ra event hiện tại.

Không dùng một ID thay cho mọi mục đích.

## 18. Chọn partition key và consumer concurrency

Một event stream có thể partition để xử lý song song. Nhưng partitioning ảnh hưởng ordering và load.

### 18.1. Key theo aggregate

Dùng orderId/customerId/reservationId nếu cần ordering theo aggregate đó. Các event cùng key thường vào cùng partition trong broker hỗ trợ key-based partitioning.

### 18.2. Hot partitions

Nếu một key xuất hiện quá nhiều hoặc partition strategy phân bố không đều, một consumer có thể bị nghẽn. Tăng số consumers không giúp nếu ordering bắt buộc tuần tự trên cùng key.

### 18.3. Parallel processing

Có thể xử lý nhiều aggregates song song nhưng serialize từng aggregate. Cần bảo đảm DB update có optimistic version hoặc unique constraints để bảo vệ race.

### 18.4. Partition count changes

Tăng số partitions có thể thay đổi mapping key→partition ở một số hệ thống, làm ordering giữa event cũ/mới phức tạp. Phải kiểm tra semantics trước khi thay đổi partition count trong migration.

## 19. Retry, backoff và poison messages

Consumer có thể thất bại vì:

- Network tạm thời.
- DB unavailable.
- Rate limit từ provider.
- Schema không tương thích.
- Payload sai.
- Business validation từ chối.
- Bug deterministic.

Không phải mọi lỗi đều nên retry giống nhau.

### 19.1. Phân loại lỗi

| Lỗi | Hành động thường cân nhắc |
| --- | --- |
| Network timeout tạm thời | Retry có backoff/jitter và giới hạn |
| DB transient failure | Retry transaction local |
| Provider 429 | Respect Retry-After, rate limit |
| Invalid schema/payload | Quarantine/DLQ và cảnh báo |
| Business rule rejection | Ghi kết quả rejected; không retry mù |
| Stale aggregate version | Reload/reconcile hoặc bỏ event cũ theo contract |
| Permission denied | Dừng retry nhanh, cảnh báo cấu hình/security |
| Missing prerequisite | Retry bounded hoặc chờ event prerequisite theo workflow |

### 19.2. Exponential backoff và jitter

Retry dồn dập có thể làm dependency đang lỗi quá tải hơn. Backoff tăng dần và jitter giúp phân tán attempts. Cần có maximum attempts, maximum age và deadline.

### 19.3. DLQ không phải thùng rác

Dead-letter queue giữ message không thể xử lý theo policy. Phải có:

- Owner.
- Alert khi count/age vượt ngưỡng.
- Error reason và correlation.
- Tool xem/replay có kiểm soát.
- Quy trình sửa schema/data trước replay.
- Audit và idempotency.
- Chính sách retention.

Message vào DLQ thường là workflow chưa hoàn tất; cần trạng thái nghiệp vụ phản ánh điều đó.

## 20. Out-of-order events và cách xử lý

Giả sử Inventory phát:

~~~text
v10: ReservationCreated
v11: ReservationConfirmed
v12: ReservationReleased
~~~

Consumer nhận v12 trước v11. Có một số chiến lược:

1. **Latest-state projection:** áp dụng version cao nhất nếu payload là snapshot đầy đủ và không cần xử lý mọi transition.
2. **Transition processing:** yêu cầu đúng version kế tiếp; nếu thiếu version thì buffer/retry hoặc lấy state từ owner.
3. **Event sourcing:** cần giữ sequence và replay tất cả facts theo contract.
4. **Timestamp last-write-wins:** chỉ dùng nếu business semantics chấp nhận và clock/ordering assumptions được kiểm soát; không dùng mặc định cho tài chính/tồn kho.

### 20.1. Version gap

Nếu current version là 10 nhưng nhận 12, consumer có thể:

- Không áp dụng và yêu cầu version 11.
- Gọi owner API lấy snapshot hiện tại rồi cập nhật.
- Đưa message vào retry/deferred queue.
- Ghi gap metric và cảnh báo.

Chọn cách dựa trên việc consumer cần mọi transition hay chỉ current state.

### 20.2. Event time và processing time

occurredAt là thời điểm business event xảy ra; processing time là lúc consumer xử lý. Hai giá trị khác nhau khi backlog/retry. Không dùng processing time để giả định thứ tự nghiệp vụ.

## 21. Concurrency và invariant phải được bảo vệ ở owner

Ví dụ inventory còn 1 sản phẩm, hai checkout đồng thời gửi ReserveInventory.

Nếu cả hai consumer đọc available=1 rồi ghi reservation, có thể tạo hai reservations cho cùng một sản phẩm. Queue không tự ngăn điều này nếu hai messages được xử lý song song hoặc đi qua các partitions khác nhau.

### 21.1. Owner quyết định

Inventory Service cần enforce invariant tại transaction boundary:

- Conditional update.
- Row lock/serializable transaction.
- Unique reservation constraint.
- Atomic compare-and-set.
- Per-SKU serialization khi phù hợp.

Event chỉ thông báo InventoryReserved hoặc ReservationRejected sau khi kết quả được commit.

### 21.2. Không giao invariant cho projection

Order hoặc Search có thể giữ stock snapshot để hiển thị, nhưng không dùng bản sao stale để quyết định reservation cuối cùng.

### 21.3. Overselling và business policy

Một số hệ thống cho phép oversell có kiểm soát/backorder. Đó là business policy phải được mô hình hóa, không phải tác dụng phụ của eventual consistency.

## 22. Saga state và trạng thái trung gian

Một checkout có thể đi qua:

~~~text
PENDING
  │
  ▼
INVENTORY_RESERVED
  │
  ▼
PAYMENT_PENDING
  │
  ├──► PAYMENT_AUTHORIZED ──► CONFIRMED
  │
  ├──► PAYMENT_DECLINED ────► RELEASE_INVENTORY ─► FAILED
  │
  └──► PAYMENT_UNKNOWN ─────► RECONCILIATION
~~~

Mỗi trạng thái cần:

- Điều kiện vào/ra.
- Owner quyết định.
- Deadline.
- Retry/compensation.
- User-visible meaning.
- Audit events.
- Recovery action.

Không dùng một boolean success=true quá sớm cho workflow nhiều bước.

### 22.1. Durable workflow

Lưu saga state trong database hoặc workflow engine có persistence. Sau restart, coordinator phải biết step cuối, command đã gửi và compensation nào còn pending.

### 22.2. Timeout không đồng nghĩa compensation ngay

Nếu Payment request timeout, có thể provider đã xử lý. Cần query/reconcile trước khi void/retry. Compensation sai có thể tạo double refund hoặc release stock của một order đã thanh toán.

## 23. CQRS và read model không tự bảo đảm consistency

CQRS tách command model và query model. Query model thường được cập nhật bất đồng bộ:

~~~text
Command → Order Service → Order DB
                         │
                         ▼
                       Outbox
                         │
                         ▼
                       Broker
                         │
                         ▼
                   Order Read Model
                         │
                         ▼
                         UI
~~~

Điều này cho phép tối ưu query và giảm coupling, nhưng read model có thể stale hoặc bị lỗi projection.

### 23.1. Cần version/watermark

Read model có thể trả appliedVersion=42. Client có thể yêu cầu version tối thiểu hoặc hiển thị trạng thái đang cập nhật.

### 23.2. Rebuild projection

Nếu projector bug đã áp dụng sai event, cần biết cách rebuild từ authoritative source/event history, xử lý tombstones và không lặp side effects.

### 23.3. Projection không phải SoR

Không nhận command nghiệp vụ bằng cách cập nhật read model trực tiếp. Command đi đến domain owner; projection chỉ phục vụ query.

## 24. Khi nào dùng đồng bộ?

Dùng request/response khi caller cần kết quả để quyết định ngay và dependency nằm trong latency budget:

- Kiểm tra authorization.
- Xác minh một reservation được tạo hay từ chối.
- Tính giá cần xác nhận trước khi chốt đơn.
- Tra cứu current state khi bản sao stale không chấp nhận được.
- Thao tác có response contract ngắn và rõ.

Cần thiết kế timeout, deadline, bulkhead, retry policy, idempotency và fallback.

### 24.1. Không giữ request mở cho workflow quá dài

Nếu operation có thể kéo dài vài phút hoặc cần nhiều human/external steps, trả 202 Accepted cùng operation ID và status endpoint/event subscription có thể phù hợp hơn.

### 24.2. Đồng bộ không có nghĩa transaction xuyên service

API trả 200 từ Payment không làm Order và Payment DB commit nguyên tử. Saga/state machine vẫn cần nếu nhiều domain thay đổi.

## 25. Khi nào dùng bất đồng bộ?

Async phù hợp khi:

- Producer không cần đợi consumer.
- Consumer có thể xử lý sau.
- Cần fan-out nhiều consumers.
- Có burst traffic và muốn buffer.
- Workload dài hoặc phụ thuộc provider chậm.
- Consumer cần replay/reprocess.
- Workflow có trạng thái và deadline rõ.

Ví dụ: gửi email, cập nhật analytics, tạo search projection, đồng bộ CRM, xử lý document hoặc webhook.

### 25.1. Không dùng async để che một API contract yếu

Nếu consumer cần dữ liệu ngay để xác nhận nghiệp vụ, phát event rồi giả định đã thành công sẽ tạo trạng thái mơ hồ. Hãy xác định command response hoặc pending workflow.

### 25.2. Async vẫn cần availability và capacity

Broker có thể đầy disk, quota, partition unavailable hoặc consumer lag. Producer cần backpressure/queue limits và policy khi không enqueue được.

## 26. Hybrid workflow: command đồng bộ, event bất đồng bộ

Ví dụ checkout:

~~~text
Client
  │ POST /checkout (idempotency key)
  ▼
Order API
  │ validate request
  │ create PENDING order + outbox
  ▼
202 Accepted + orderId
  │
  ▼
Workflow / consumers
  ├── Inventory.reserve
  ├── Payment.authorize
  └── Order state transitions
           │
           ▼
       OrderConfirmed event
           │
           ├──► Notification
           ├──► Fulfillment
           └──► Analytics
~~~

API xác nhận đã tiếp nhận và tạo operation bền vững. Workflow tiếp tục bất đồng bộ. User có thể query order status hoặc nhận update. Nếu business yêu cầu xác nhận payment ngay trước khi trả response, có thể đồng bộ một phần rồi dùng event cho hậu xử lý.

## 27. Consistency models và lựa chọn theo use case

| Use case | Consistency expectation | Thiết kế có thể phù hợp |
| --- | --- | --- |
| Số dư tài khoản/ledger | Invariant chặt, không double spend | Transaction ở owner, concurrency control, idempotency |
| Tồn kho reservation | Không vượt rule capacity | Atomic conditional update/locking ở Inventory |
| Search product index | Chấp nhận trễ ngắn | Event projection + freshness SLO |
| Email notification | Có thể gửi sau | Queue + retry + DLQ + idempotency |
| Analytics dashboard | Chấp nhận batch/lag được công bố | Warehouse pipeline + watermark |
| Order status UI | Có thể pending nhưng không lùi version | Owner status + version-aware projection |
| Payment provider result | Timeout có thể unknown | Idempotency + query/reconciliation |
| Customer profile | Read-your-writes mong muốn | Owner read hoặc version-aware projection |

Không cần strong consistency cho mọi bản sao. Cần **strong guarantee ở nơi invariant yêu cầu**, và freshness/consistency contract rõ cho những bản sao còn lại.

## 28. Ví dụ: Payment và Order bị lệch

### 28.1. Tình huống

1. Order tạo PENDING.
2. Payment nhận authorize và commit AUTHORIZED.
3. Payment publish PaymentAuthorized.
4. Broker nhận event.
5. Order consumer lỗi do schema parse.
6. Order vẫn PENDING.

Async đã tách thời gian, nhưng không tự hoàn tất workflow.

### 28.2. Cách điều tra

- Payment SoR có authorization không?
- Outbox/publisher đã publish event chưa?
- Broker offset/retention và consumer lag?
- DLQ có event lỗi?
- Schema version có tương thích?
- Order consumer đã commit inbox/order update chưa?
- Event có bị duplicate/out-of-order?
- Có status reconciliation job không?

### 28.3. Cách khôi phục

- Sửa consumer/schema compatibility.
- Replay message theo idempotency.
- Query Payment owner để xác nhận state.
- Order thực hiện transition hợp lệ.
- Kiểm tra invoice/notification/fulfillment side effects.
- Đối soát payment references và order states.

Không cập nhật trực tiếp Order DB bằng SQL để che symptom nếu state machine/audit/event không được thực hiện.

## 29. Ví dụ: Event cũ ghi đè projection mới

### 29.1. Tình huống

- CustomerUpdated v12 được xử lý trước.
- CustomerUpdated v11 được retry và đến sau.
- Projection áp dụng v11, dữ liệu lùi.

### 29.2. Biện pháp

- Lưu aggregate version trong projection.
- Chỉ apply nếu incoming version lớn hơn current version khi event là full snapshot.
- Với delta events, phát hiện gap và xử lý theo sequence.
- Dùng key partition theo aggregate nếu ordering per entity cần thiết.
- Có replay/rebuild nếu projector đã sai.
- Ghi metric stale-event dropped và version gaps.

Không dùng timestamp đơn thuần nếu clocks hoặc concurrent updates có thể gây thứ tự không đúng.

## 30. Ví dụ: Consumer chạy xong nhưng ack thất bại

### 30.1. Tình huống

Notification gửi email thành công. Process crash trước khi ack message. Broker redeliver và email được gửi lần hai.

### 30.2. Cách giải quyết

- Tạo notification operation ID ổn định từ business event/recipient/template purpose.
- Lưu trạng thái send và provider reference.
- Dùng provider idempotency nếu có.
- Nếu provider không hỗ trợ idempotency, thiết kế dedup và reconciliation theo khả năng, chấp nhận/giảm rủi ro duplicate.
- Ack sau khi local processing state bền vững theo protocol.

Không thể đảm bảo external side effect exactly-once chỉ bằng cách thêm một inbox table nếu email provider không tham gia transaction.

## 31. Ví dụ: Async inventory tạo oversell

### 31.1. Tình huống

Order phát ReserveRequested cho SKU còn một sản phẩm. Hai consumer workers nhận hai requests cùng lúc. Cả hai đọc available=1 trước khi ghi reservation.

### 31.2. Lỗi thiết kế

Đội cho rằng queue đảm bảo tuần tự nhưng requests có thể đi qua hai partitions hoặc hai worker concurrency. Không có atomic condition ở Inventory DB.

### 31.3. Sửa

Inventory owner dùng transaction/conditional update hoặc serialization theo SKU, unique reservation keys và trả event InventoryReserved hoặc ReservationRejected sau commit. Order chờ kết quả và hiển thị pending.

## 32. Backpressure và queue growth

Async có thể đẩy backlog ra sau broker, làm API producer trông khỏe trong khi workflow ngày càng chậm.

Ví dụ producer phát 1.000 messages/giây, consumer xử lý 700 messages/giây. Backlog tăng khoảng 300 messages/giây trong điều kiện đơn giản.

Cần theo dõi:

- Queue depth.
- Oldest message age.
- Consumer throughput.
- Processing duration.
- Retry rate.
- DLQ count/age.
- Provider quota/429.
- Storage capacity và retention.

### 32.1. Scale consumer không phải luôn là giải pháp

Nếu consumer bị giới hạn bởi DB hoặc external API quota, thêm workers có thể làm dependency quá tải. Phải xác định bottleneck trước khi scale.

### 32.2. Queue limit và admission control

Nếu queue đầy hoặc message age vượt deadline, cần policy: reject, defer, degrade, shed load hoặc chuyển trạng thái. Không thể nhận vô hạn công việc và giả định nó sẽ xử lý xong.

### 32.3. Deadline propagation

Mỗi business operation có deadline. Consumer cần biết message còn hữu ích không. Ví dụ email giao dịch có thể cần gửi trong vài phút; một recommendation refresh cũ có thể bỏ qua nếu đã có version mới hơn.

## 33. Retry amplification và poison message

Retry nhiều tầng có thể tạo tải tăng mạnh:

~~~text
Gateway retry Order
    ↓
Order retry Payment
    ↓
Payment retry Provider
~~~

Một request người dùng có thể tạo nhiều attempts ở từng tầng. Cần một retry budget/deadline tổng thể, backoff/jitter và idempotency.

Poison message có thể làm consumer retry mãi một partition hoặc chặn progress tùy broker/consumer model. Cần phân loại lỗi, bounded retries, DLQ và quy trình repair/replay.

## 34. Reconciliation là một phần của thiết kế

Event delivery không thay thế reconciliation cho các domain critical.

Ví dụ đối soát Order và Payment:

~~~text
Order records
   │
   ├── paymentId / expected amount / state
   ▼
Reconciliation job
   ▲
   ├── Payment authoritative records
   │
   └── Provider settlement/status
~~~

Tìm:

- Order PENDING quá deadline nhưng Payment đã AUTHORIZED.
- Payment CAPTURED không có Order reference hợp lệ.
- Amount/currency không khớp.
- Duplicate authorization.
- Refund đã settle nhưng Order chưa cập nhật.
- Event bị mất/consumer DLQ.

### 34.1. Reconciliation không nên ghi bừa

Job xác định mismatch và gọi owner API/command hoặc tạo review item. Mọi correction cần audit, idempotency và rule nghiệp vụ.

### 34.2. Frequency theo rủi ro

Payment/ledger có thể cần đối soát thường xuyên; search index có thể rebuild theo nhu cầu. Không áp cùng cadence cho mọi dataset.

### 34.3. Reconciliation SLO

Định nghĩa thời gian tối đa một mismatch critical được phát hiện và giải quyết, cùng số lượng/age mismatch được phép. Đây là một phần của business correctness.

## 35. Observability cho async workflow

Cần theo dõi từ producer tới business completion:

- Event ID, correlation ID, causation ID.
- Aggregate ID/version.
- Producer commit/publish timestamp.
- Broker enqueue/consume time.
- Consumer start/end/ack.
- Retry attempt và error class.
- Projection applied version.
- Workflow/saga state.
- Completion deadline và final outcome.

### 35.1. Trace context

Propagate W3C Trace Context hoặc cơ chế tương đương qua message headers. Consumer tạo span liên kết với producer trace; workflow dài có thể cần span links thay vì giữ một trace cực dài.

### 35.2. Metrics không dùng high-cardinality IDs

Không đưa eventId/orderId/customerId vào metric labels. Dùng logs/traces có kiểm soát để correlation; metrics dùng labels hữu hạn như service, operation, topic, outcome, region.

### 35.3. Dashboard theo business outcome

Một dashboard queue xanh không có nghĩa checkout đã hoàn tất. Cần đo tỷ lệ Order chuyển PENDING→CONFIRMED trong deadline, cùng Payment/Inventory consistency.

## 36. Testing để chứng minh tính đúng đắn

### 36.1. Unit/domain tests

- State transitions.
- Idempotency behavior.
- Version checks.
- Compensation rules.
- Invalid/duplicate command handling.
- Business invariants.

### 36.2. Integration tests

- DB transaction + outbox atomicity.
- Inbox dedup và concurrent delivery.
- Broker redelivery.
- Schema compatibility.
- Retry/DLQ.
- Consumer restart.
- Offset/checkpoint behavior.

### 36.3. Concurrency tests

- Hai reservations tranh SKU cuối.
- Hai updates cùng aggregate version.
- Consumer xử lý duplicate đồng thời.
- Producer retry trong lúc timeout.
- Out-of-order event và version gap.

### 36.4. Failure injection

Giả lập:

1. DB commit thành công nhưng publisher bị kill.
2. Broker nhận event nhưng response bị mất.
3. Consumer commit DB nhưng ack thất bại.
4. Provider trả 429/503/timeout.
5. Message đến sai thứ tự.
6. Consumer bị dừng đủ lâu để queue backlog.
7. Schema producer đổi trước consumer.
8. DLQ replay sau khi fix.
9. Database restore về checkpoint cũ.
10. Duplicate webhook từ provider.

### 36.5. Kiểm tra end-to-end

Xác nhận business invariants và user-facing SLI sau mỗi fault. Một test chỉ xác nhận HTTP 202 hoặc broker enqueue không chứng minh workflow đã hoàn thành.

## 37. Những câu hỏi khi thiết kế một async flow

Trước khi publish event/command, trả lời:

1. Message là command hay fact?
2. Ai là authoritative owner của trạng thái?
3. Producer commit và publish được liên kết thế nào?
4. Delivery guarantee thực tế là gì?
5. Duplicate có thể xảy ra ở đâu?
6. Consumer idempotency key là gì?
7. Ordering cần ở mức nào: global, partition, aggregate hay không cần?
8. Concurrent updates được bảo vệ tại đâu?
9. Event version và schema compatibility ra sao?
10. Timeout/unknown/pending states được biểu diễn thế nào?
11. Retry, backoff, DLQ và replay do ai sở hữu?
12. Freshness/completion deadline là bao lâu?
13. User nhìn thấy trạng thái gì trong thời gian chờ?
14. Có reconciliation cho mismatch critical không?
15. Có cách rebuild projection và restore sau disaster không?
16. PII/secret nào đi trong payload và retention bao lâu?
17. Ai nhận alert khi consumer lag hoặc workflow kẹt?
18. Có test chứng minh duplicate, out-of-order và partial failure không?

## 38. Anti-patterns thường gặp

**1. Publish sau commit mà không outbox.**  
DB có thể commit nhưng event không bao giờ được publish.

**2. Publish trước commit.**  
Consumer có thể thấy fact của transaction bị rollback.

**3. Cho rằng broker nhận message nghĩa là business action hoàn tất.**  
Producer acknowledgement và consumer completion là hai mốc khác nhau.

**4. Consumer không idempotent.**  
Redelivery tạo payment, reservation hoặc email trùng.

**5. Dùng timestamp làm ordering tuyệt đối.**  
Clock skew, retries và concurrent writes có thể làm sai thứ tự.

**6. Dùng một global partition/queue để giả định ordering toàn hệ thống.**  
Throughput và hot-key bottlenecks tăng; ordering vẫn cần semantics cụ thể.

**7. Retry vô hạn.**  
Một dependency lỗi làm backlog và tải tăng không giới hạn.

**8. DLQ không có owner.**  
Message bị bỏ quên khiến dữ liệu không hội tụ.

**9. Chuyển mọi API sang event.**  
Caller cần kết quả ngay nhưng chỉ nhận một thông báo đã enqueue.

**10. Dùng 202 như business success.**  
Request đã tiếp nhận không có nghĩa workflow hoàn tất.

**11. Không có UNKNOWN state.**  
Timeout bị coi là thất bại, dẫn tới duplicate side effects.

**12. Projection được dùng làm source of truth.**  
Bản sao stale quyết định giao dịch quan trọng.

**13. Event snapshot và delta bị xem như nhau.**  
Snapshot có thể bỏ qua version cũ; delta cần xử lý đầy đủ thứ tự/gap.

**14. Chỉ test happy path.**  
Không phát hiện crash giữa commit/ack, duplicate, lag hoặc schema mismatch.

**15. Không có reconciliation.**  
Một số mismatch hiếm có thể tồn tại vô hạn.

**16. Cho rằng async luôn tăng reliability.**  
Broker, consumer và workflow state trở thành các dependencies mới.

**17. Chuyển consistency complexity cho frontend.**  
UI không nên tự đoán trạng thái nghiệp vụ từ nhiều bản sao không có contract.

**18. Không định nghĩa retention/replay.**  
Message hết hạn hoặc replay ngoài dự kiến làm workflow thiếu/sai dữ liệu.

## 39. Checklist triển khai async flow

### Semantics và ownership

- [ ] Phân biệt command và domain event.
- [ ] Có authoritative owner cho mỗi business state.
- [ ] Định nghĩa trạng thái PENDING/UNKNOWN/COMPLETED/FAILED nếu workflow dài.
- [ ] Có contract về freshness và completion deadline.
- [ ] Snapshot/projection được phân biệt với SoR.

### Producer

- [ ] State change và outbox record commit nguyên tử.
- [ ] Event ID, aggregate ID/version, correlation/causation rõ.
- [ ] Payload tối thiểu và schema versioned.
- [ ] Publish retry/confirm và retention có policy.
- [ ] Không publish fact trước khi business change durable.

### Broker

- [ ] Delivery guarantee và durability settings đã hiểu.
- [ ] Partition/key strategy phù hợp ordering.
- [ ] Retention/capacity/quota/HA được thiết kế.
- [ ] DLQ và replay có owner/runbook.
- [ ] Backpressure/admission control có policy.

### Consumer

- [ ] Idempotency/dedup tại boundary phù hợp.
- [ ] Inbox/state update atomic khi cần.
- [ ] Version/order/gap được xử lý theo contract.
- [ ] Retry bounded, backoff/jitter và error classification.
- [ ] Poison message được quarantine và alert.
- [ ] Side effects ngoài DB có idempotency/reconciliation.

### Workflow và trải nghiệm

- [ ] Saga state durable nếu process dài.
- [ ] Compensation và UNKNOWN handling rõ.
- [ ] UI phản ánh trạng thái thực, không báo hoàn tất quá sớm.
- [ ] Read-your-writes/freshness expectations được xác định.
- [ ] Business SLI đo completion end-to-end.

### Vận hành và kiểm chứng

- [ ] Theo dõi outbox age, consumer lag, oldest message age, retries, DLQ.
- [ ] Trace context xuyên message.
- [ ] Có reconciliation cho data critical.
- [ ] Test duplicate, out-of-order, concurrency và crash windows.
- [ ] Có replay/rebuild/restore procedure.
- [ ] Security, PII, retention và audit được xử lý.

## 40. Bài tập tình huống

### Bài A — Event publish thành công nhưng dữ liệu chưa đổi

Order DB đã commit PENDING; broker báo nhận OrderCreated; Inventory vẫn chưa reserve.

**Câu hỏi:** đây có phải lỗi consistency ngay lập tức?

**Gợi ý:** có thể là trạng thái trung gian hợp lệ. Cần biết workflow deadline, consumer lag, completion SLI và trạng thái Order. Nếu vượt deadline hoặc message DLQ thì cần điều tra/reconcile.

### Bài B — Consumer nhận message hai lần

Consumer gửi email, commit local state nhưng crash trước ack. Broker redeliver.

**Câu hỏi:** làm sao giảm email duplicate?

**Gợi ý:** notification operation key ổn định, inbox/dedup và provider idempotency nếu hỗ trợ. Local DB transaction không thể tự atomic với external email provider.

### Bài C — Out-of-order Customer events

Projection nhận version 12 rồi version 11.

**Câu hỏi:** có nên áp dụng version 11?

**Gợi ý:** nếu payload là full snapshot và projection chỉ cần latest state, bỏ version cũ. Nếu event là delta cần mọi transition, phát hiện gap và fetch/replay theo contract.

### Bài D — Hai checkout tranh sản phẩm cuối

Hai ReserveRequested được xử lý đồng thời ở hai workers.

**Câu hỏi:** queue có bảo đảm không oversell?

**Gợi ý:** không. Inventory owner phải enforce atomic reservation/concurrency control ở DB/domain boundary, dùng idempotency key.

### Bài E — Payment timeout

Order gọi Payment, timeout; Payment đã authorize nhưng response không tới.

**Câu hỏi:** có nên retry với key mới?

**Gợi ý:** không. Giữ UNKNOWN/PENDING, dùng cùng idempotency key và query/reconcile Payment owner trước khi tạo attempt mới.

### Bài F — Queue lag tăng nhưng API vẫn khỏe

Producer trả 202, consumer chỉ xử lý 50% tốc độ publish.

**Câu hỏi:** có thể tuyên bố hệ thống khỏe vì HTTP 5xx thấp không?

**Gợi ý:** không. Đo oldest message age, workflow completion SLO và backlog; scale chỉ khi downstream capacity cho phép.

### Bài G — DLQ chứa event schema mới

Producer thêm enum PARTIALLY_REFUNDED; consumer cũ parse fail.

**Câu hỏi:** xử lý thế nào?

**Gợi ý:** dừng retry vô hạn, xác định contract compatibility, nâng consumer hoặc adapter, replay có idempotency, kiểm tra projection và business outcomes.

### Bài H — Event cũ ghi đè dữ liệu mới

Consumer áp dụng snapshot cũ sau khi nhận snapshot mới.

**Câu hỏi:** cần metadata gì?

**Gợi ý:** aggregate version/sequence, event ID và semantics snapshot/delta; consumer chỉ apply theo policy version.

### Bài I — Async không giải quyết transaction

Order, Payment và Inventory cần cùng thành công hoặc cùng thất bại.

**Câu hỏi:** có thể chỉ phát ba events không?

**Gợi ý:** cần saga/state machine và compensation. Nếu invariant thực sự cần atomic transaction, xem lại domain boundary/data ownership trước khi phân tán.

### Bài J — User thấy trạng thái cũ sau khi cập nhật

Customer API trả email mới nhưng profile page đọc projection cũ.

**Câu hỏi:** lựa chọn nào?

**Gợi ý:** read-your-writes bằng owner read/version token hoặc UI pending/optimistic update; đặt freshness SLO cho projection.

### Bài K — Broker báo exactly-once

Payment consumer xử lý event trong transaction broker nhưng gọi external payment provider.

**Câu hỏi:** điều gì vẫn có thể bị duplicate?

**Gợi ý:** external side effect nằm ngoài broker transaction. Cần idempotency key/provider lookup và reconciliation.

### Bài L — Restore database sau sự cố

Order DB restore về version cũ, consumer offsets vẫn ở thời điểm mới.

**Câu hỏi:** có thể tiếp tục consume từ offset hiện tại?

**Gợi ý:** không mặc định. Cần xác định checkpoint/state, replay hoặc rebuild projection, dedup và reconcile để không mất events cần thiết.

## 41. Runbook: async workflow bị kẹt

1. Xác định business operation ID, event ID, aggregate ID và thời điểm bắt đầu.
2. Xem user-facing status và deadline của workflow.
3. Kiểm tra authoritative source đã commit state gì.
4. Kiểm tra outbox/publisher status.
5. Kiểm tra broker enqueue, partition, retention và offset.
6. Kiểm tra consumer lag, retries, DLQ và error class.
7. Kiểm tra consumer DB transaction/inbox/projection version.
8. Kiểm tra downstream provider/DB capacity và rate limit.
9. Xác định message có thể replay an toàn không, idempotency key nào được dùng.
10. Nếu kết quả side effect chưa rõ, query/reconcile owner trước khi retry.
11. Thực hiện repair/replay theo runbook và ghi audit.
12. Xác nhận business state cuối, freshness SLO và user experience.

## 42. Runbook: phát hiện dữ liệu không nhất quán

1. Xác định hai bản sao đang khác nhau và semantics của từng bản.
2. Xác định authoritative owner và version/watermark.
3. Kiểm tra event history, outbox/inbox, broker offsets và DLQ.
4. Phân loại duplicate, missing, stale, out-of-order, transformation error hay concurrent update.
5. Tìm những consumers khác có thể bị ảnh hưởng.
6. Đưa correction/replay qua owner-controlled command.
7. Không sửa trực tiếp projection nếu chưa hiểu nguyên nhân và replay effects.
8. Chạy reconciliation theo business invariant.
9. Kiểm tra downstream projections và external side effects.
10. Cập nhật alert/runbook/test để ngăn tái phát.

## 43. Câu hỏi cho architecture review

1. Async đang giải quyết coupling cụ thể nào?
2. Business operation được coi là hoàn thành ở mốc nào?
3. Ai sở hữu trạng thái authoritative?
4. Producer commit và publish có atomic không?
5. Consumer có thể nhận duplicate không?
6. Ordering cần ở phạm vi nào?
7. Có concurrent writes lên cùng aggregate không?
8. Timeout có thể tạo UNKNOWN result không?
9. Retry có giới hạn và deadline không?
10. DLQ ai theo dõi và ai quyết định replay?
11. Projection freshness SLO là gì?
12. Có read-your-writes requirement không?
13. Side effects bên ngoài có idempotency không?
14. Có reconciliation khi event bị mất/consumer lỗi không?
15. Broker/consumer outage ảnh hưởng user journey thế nào?
16. Có test crash giữa commit, publish, consume và ack không?
17. Có kế hoạch replay/rebuild sau restore không?
18. Payload có PII/secret và retention phù hợp không?

## 44. Tổng kết

Chuyển sang bất đồng bộ có thể giúp producer và consumer hoạt động độc lập về thời gian, hấp thụ burst, fan-out và xử lý công việc dài. Nhưng message queue chỉ là một phần của hệ thống phân tán. **Tính nhất quán phải được thiết kế ở business state, transaction boundary, event semantics, concurrency control và recovery process.**

Một thiết kế đáng tin cậy cần:

1. **Rõ ownership:** domain nào quyết định giá trị chuẩn và ai được ghi.
2. **Publish đáng tin:** outbox hoặc cơ chế liên kết commit với event.
3. **Consumer an toàn:** idempotency, inbox/dedup và version/order handling.
4. **Workflow có trạng thái:** saga, pending/unknown, deadline và compensation.
5. **Dữ liệu bản sao có hợp đồng:** freshness, read-your-writes, rebuild và retention.
6. **Phát hiện sai lệch:** metrics, tracing, DLQ, reconciliation và runbooks.
7. **Kiểm chứng failure modes:** duplicate, out-of-order, concurrent writes, timeout và crash windows.

Hãy dùng đồng bộ khi caller cần kết quả để ra quyết định ngay, bất đồng bộ khi công việc có thể hoàn thành sau và cần tách thời gian, hoặc kết hợp hai cách theo từng bước. **Không giao tính đúng đắn cho transport layer**: broker chuyển message; domain owner và consumer phải cùng thực hiện các quy tắc để trạng thái nghiệp vụ cuối cùng đúng.
