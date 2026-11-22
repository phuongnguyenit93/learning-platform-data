# Ngữ nghĩa giao nhận, trùng lặp và giới hạn của exactly-once

## Mục tiêu học tập

Trong kiến trúc sự kiện (*event-driven architecture*), các thành phần giao tiếp bằng event được lưu, truyền và xử lý qua broker, queue hoặc event log. Việc một message đã được gửi, broker đã xác nhận, consumer đã nhận hay nghiệp vụ đã hoàn tất là những mốc khác nhau. Nếu không phân biệt chúng, hệ thống dễ mất sự kiện, xử lý trùng hoặc tuyên bố sai rằng giao dịch đã được thực hiện đúng một lần.

Bài học thuộc chương **Kiến trúc sự kiện**, tập trung vào **ngữ nghĩa giao nhận (delivery semantics), hiện tượng trùng lặp (duplicate delivery), thứ tự xử lý và giới hạn của exactly-once**. Đây là nền tảng để thiết kế hệ thống có thể phục hồi khi process chết, mạng chập chờn, consumer timeout, broker giao lại message hoặc downstream không phản hồi rõ kết quả.

Sau bài học, bạn có thể:

- Phân biệt at-most-once, at-least-once và exactly-once theo phạm vi được bảo đảm.
- Mô tả các mốc publish, persist, deliver, acknowledge, commit và hoàn tất nghiệp vụ.
- Giải thích vì sao message có thể được giao hoặc xử lý nhiều lần dù producer chỉ gửi một lần.
- Thiết kế consumer idempotent, deduplication, inbox/outbox và transactional boundary.
- Phân biệt exactly-once trong phạm vi broker/stream processor với hiệu ứng nghiệp vụ end-to-end.
- Xử lý ordering, retry, poison message, visibility timeout, rebalance và replay.
- Định nghĩa SLI/SLO, kiểm thử lỗi, quan sát và chi phí cho hệ thống sự kiện.
- Đánh giá giải pháp theo độ tin cậy, bảo mật, hiệu năng, chi phí và khả năng vận hành của **Cloud Architecture**.

## 1. Vì sao ngữ nghĩa giao nhận quan trọng?

Giả sử ứng dụng đặt phòng ghi nhận một booking đã thanh toán. Sau khi transaction trong database commit, hệ thống phát event BookingConfirmed để gửi email, cập nhật tồn kho và ghi dữ liệu phân tích.

Có nhiều tình huống có thể xảy ra:

- Producer ghi booking xong nhưng process chết trước khi publish event.
- Broker lưu event nhưng phản hồi publish bị mất; producer không biết event đã được lưu hay chưa.
- Broker gửi event tới consumer; consumer thực hiện side effect nhưng chết trước khi acknowledge.
- Consumer acknowledge trước khi transaction database commit; process chết và event không còn được giao lại.
- Consumer xử lý thành công nhưng ACK trên mạng bị mất, broker giao lại event.
- Consumer nhận hai bản sao do producer retry hoặc do broker redelivery.
- Hai event của cùng booking đến theo thứ tự khác với thứ tự nghiệp vụ.

Do đó, câu “gửi event một lần” không đồng nghĩa “mọi subscriber thực hiện tác dụng phụ đúng một lần”.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    participant C as Consumer
    participant D as Database
    P->>B: Publish event E
    B-->>P: Publish ack
    B->>C: Deliver E
    C->>D: Commit side effect
    Note over C,D: Process có thể chết sau commit
    C--xB: ACK bị mất
    B->>C: Redeliver E
    C->>D: Nhận diện duplicate
    C-->>B: ACK sau khi xác nhận đã xử lý
~~~

Điểm mấu chốt là **broker và consumer không cùng một transaction với mọi hệ thống ngoài**. ACK bị mất có thể khiến broker không biết consumer đã hoàn tất hay chưa. Từ góc nhìn broker, giao lại bảo vệ message; từ góc nhìn nghiệp vụ, giao lại có thể gây duplicate nếu consumer không an toàn khi chạy lại.

## 2. Phân biệt publish, deliver, acknowledge và xử lý nghiệp vụ

Một event đi qua nhiều mốc. Cần định nghĩa mốc nào là cam kết của từng thành phần.

| Mốc | Ý nghĩa | Điều chưa thể kết luận |
| --- | --- | --- |
| Event được tạo | Producer tạo event trong bộ nhớ hoặc chuẩn bị payload | Event chưa chắc đã bền vững |
| Publish được gửi | Producer gửi request tới broker | Broker chưa chắc đã ghi nhận |
| Broker xác nhận publish | Broker trả ACK theo semantics cấu hình | Consumer chưa chắc đã nhận hoặc xử lý |
| Broker persist | Message được lưu theo durability policy | Không tự đảm bảo mọi subscriber đã xử lý |
| Deliver | Broker chuyển message đến consumer | Consumer có thể chưa hoàn tất |
| Consumer nhận message | Process đã nhận payload | Side effect chưa chắc đã commit |
| Side effect commit | Database hoặc hệ thống ngoài đã áp dụng thay đổi | ACK có thể chưa được gửi/ghi nhận |
| Acknowledge/offset commit | Consumer báo broker message đã được xử lý tới một mốc | Không nhất thiết nghiệp vụ downstream hoàn tất |
| Business completion | Điều kiện nghiệp vụ cuối cùng đạt và được xác nhận | Phải dựa vào trạng thái nghiệp vụ, không chỉ broker metric |

Ví dụ, queue có thể được cấu hình xóa message khi consumer ACK. Nếu consumer ACK trước khi commit database, crash có thể gây mất tác dụng phụ vì broker không giao lại. Nếu consumer commit database rồi mới ACK, crash ở giữa có thể tạo duplicate delivery. Consumer phải xử lý tình huống thứ hai một cách an toàn.

### 2.1. ACK không phải lúc nào cũng giống nhau

Một số broker dùng ACK/NACK cho từng message; một số dùng visibility timeout và delete message; hệ thống log/partition như Kafka dùng offset commit. Có broker xác nhận publish, nhưng consumer acknowledgement là luồng riêng.

Khi đọc tài liệu dịch vụ, cần phân biệt:

- **Publisher confirm:** broker đã chấp nhận/persist publish theo cấu hình nào?
- **Consumer acknowledgement:** message có thể bị xóa hoặc không được giao lại trong điều kiện nào?
- **Offset commit:** consumer đã ghi nhận tiến độ đọc đến offset nào?
- **Replication acknowledgement:** bao nhiêu replica hoặc mức durability được xác nhận?
- **Transaction commit:** output và tiến độ có được commit nguyên tử trong phạm vi nào?

Không sử dụng từ ACK chung chung trong ADR hoặc runbook. Hãy ghi rõ ai xác nhận, xác nhận điều gì và khi nào message được coi là an toàn để bỏ qua.

## 3. Ba ngữ nghĩa giao nhận cơ bản

### 3.1. At-most-once: tối đa một lần

Với at-most-once, hệ thống ưu tiên không lặp lại message. Khi xảy ra lỗi tại một số thời điểm, message có thể bị mất hoặc không được xử lý lại.

Ví dụ consumer lấy message và ACK/xóa message trước khi thực hiện side effect. Nếu process chết sau ACK nhưng trước khi ghi database, broker không còn lý do để giao lại message.

**Lợi ích:** tránh hoặc hạn chế xử lý lặp, có thể đơn giản hơn cho tác vụ chấp nhận bỏ sót một số mẫu.

**Đánh đổi:** có thể mất message/tác dụng phụ khi lỗi. Không phù hợp với giao dịch tài chính, đặt chỗ hoặc event quan trọng nếu không có cơ chế reconciliation khác.

At-most-once không có nghĩa mọi message luôn được xử lý một lần. Nó có thể là **zero times** nếu message bị mất hoặc bị bỏ qua.

### 3.2. At-least-once: ít nhất một lần

Với at-least-once, broker/consumer được thiết kế để giao lại khi không nhận được xác nhận phù hợp. Cách này giảm nguy cơ mất message nhưng duplicate có thể xảy ra.

Ví dụ:

1. Consumer nhận event.
2. Consumer ghi khoản thanh toán vào database thành công.
3. Consumer chết trước khi ACK.
4. Broker giao lại event.
5. Consumer thứ hai nhận lại cùng event.

Nếu side effect không idempotent, số dư hoặc số lần phát hành hóa đơn có thể tăng hai lần.

**Lợi ích:** phù hợp với nghiệp vụ quan trọng khi kết hợp deduplication, idempotency và đối soát.

**Đánh đổi:** phải thiết kế xử lý lặp, retry, poison message và lưu trạng thái đã xử lý. Đây là semantics phổ biến trong nhiều hệ thống queue vì ưu tiên không mất message.

### 3.3. Exactly-once: xác định rõ “một lần” ở phạm vi nào

Exactly-once thường mô tả một bảo đảm mạnh hơn: một kết quả được phản ánh đúng một lần trong **phạm vi giao dịch và hệ thống đã xác định**. Nhưng nó không tự động kéo dài xuyên qua mọi broker, consumer, database, API ngoài và con người vận hành.

Có thể có các phạm vi khác nhau:

- Broker không tạo duplicate trong một điều kiện cấu hình.
- Producer retry nhưng broker nhận diện cùng producer sequence/transaction.
- Stream processor chỉ commit output một lần theo checkpoint/transaction của framework.
- Consumer cập nhật một database đúng một lần theo unique key/idempotency.
- Nghiệp vụ end-to-end chỉ phát hành một hóa đơn hoặc ghi nhận một khoản trừ tiền.

Những bảo đảm này không tương đương. Cần hỏi **exactly-once đối với đối tượng nào, trong transaction boundary nào, với loại lỗi nào và bao gồm downstream nào?**

### 3.4. So sánh

| Tiêu chí | At-most-once | At-least-once | Exactly-once trong phạm vi xác định |
| --- | --- | --- | --- |
| Duplicate delivery | Thường tránh bằng cách không giao lại | Có thể xảy ra | Được loại trừ trong phạm vi cơ chế bảo đảm |
| Mất message khi lỗi | Có thể xảy ra | Được hạn chế theo durability/retention và recovery policy | Phụ thuộc phạm vi transaction và durability |
| Consumer idempotent | Vẫn hữu ích | Rất quan trọng | Vẫn cần với hiệu ứng ngoài boundary |
| Độ phức tạp | Có thể thấp hơn | Cao hơn do retry/dedup | Cao và có điều kiện |
| Ví dụ phù hợp | Telemetry có thể mất một số mẫu | Booking event, hóa đơn, cập nhật dữ liệu | Stream transaction hoặc DB operation có unique key |
| Điều phải làm rõ | Tỷ lệ mất được chấp nhận? | Duplicate được ngăn thế nào? | Exactly-once ở tầng nào, có gồm external side effect không? |

Không có lựa chọn luôn tốt nhất. Mục tiêu là chọn semantics phù hợp với mức độ quan trọng của dữ liệu và xây dựng cơ chế bảo đảm nghiệp vụ cần thiết.

## 4. Duplicate delivery xảy ra như thế nào?

### 4.1. Producer retry sau khi mất phản hồi

Producer gửi event, broker persist thành công nhưng response ACK bị mất trên mạng. Producer timeout và gửi lại. Broker có thể nhìn thấy hai publish độc lập nếu protocol không có idempotent producer hoặc deduplication key phù hợp.

### 4.2. Consumer xử lý xong nhưng ACK thất bại

Consumer commit DB nhưng ACK không đến broker hoặc ACK bị mất. Broker thấy message chưa được xác nhận nên giao lại.

### 4.3. Visibility timeout hết hạn

Trong một số queue, message trở nên invisible trong thời gian lease/visibility timeout sau khi được nhận. Nếu worker xử lý lâu hơn thời hạn mà không gia hạn, message có thể xuất hiện lại và được worker khác nhận trong khi worker đầu vẫn đang chạy.

### 4.4. Consumer rebalance hoặc restart

Với hệ thống partition/offset, consumer đã xử lý record nhưng chưa commit offset. Khi process restart hoặc partition được gán cho consumer khác, record được đọc lại từ offset cũ. Nếu output đã commit trước đó, duplicate side effect có thể xảy ra.

### 4.5. Replay, redrive và backfill

Người vận hành chủ động phát lại event từ DLQ, archive hoặc offset cũ. Một số event có thể đã được xử lý thành công trong lần chạy đầu. Nếu không phân biệt replay và event mới, hệ thống có thể nhân đôi side effect.

### 4.6. Producer tạo event mới cho cùng nghiệp vụ

Ngay cả khi broker không duplicate message, producer có thể phát hai event ID khác nhau cho cùng một thao tác do client retry. Deduplicate bằng message ID sẽ không phát hiện được hai event có ID khác nhau nhưng cùng mục tiêu nghiệp vụ.

Có ít nhất hai lớp duplicate cần xử lý: duplicate ở cấp **message/event ID** và duplicate ở cấp **business operation/key**.

## 5. Consumer idempotent: nền tảng cho at-least-once

Một consumer idempotent có thể nhận message nhiều lần mà trạng thái nghiệp vụ cuối vẫn giống như chỉ xử lý một lần.

### 5.1. Thiết kế inbox/deduplication table

Ví dụ bảng inbox:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng transaction database:

1. Thử insert cặp consumer_name + event_id.
2. Nếu unique constraint báo đã tồn tại và event đã được xử lý, bỏ qua tác dụng phụ.
3. Nếu insert thành công, áp dụng thay đổi nghiệp vụ.
4. Đánh dấu processed và commit.
5. Chỉ sau khi commit mới ACK message/commit offset theo semantics broker.

Unique constraint là cơ chế đồng bộ giữa các worker; chỉ kiểm tra bằng câu SELECT trước INSERT là chưa đủ vì hai consumer có thể cùng đọc “chưa tồn tại” rồi cùng ghi. Ràng buộc duy nhất ở database giải quyết race condition tại nơi lưu trữ.

### 5.2. Cùng transaction là điều kiện quan trọng

Nếu consumer ghi inbox ở database A rồi cập nhật trạng thái nghiệp vụ trong database B, hai thao tác không nguyên tử. Có thể ghi inbox thành công rồi lỗi khi cập nhật B; lần giao lại sẽ bị bỏ qua dù nghiệp vụ chưa hoàn tất.

Ngược lại, nếu cập nhật nghiệp vụ trước rồi ghi inbox thất bại, lần giao lại có thể lặp tác dụng phụ.

Các hướng xử lý:

- Inbox record và business state nằm trong cùng database transaction.
- Dùng transaction coordinator nếu hệ thống hỗ trợ và chấp nhận trade-off.
- Dùng workflow/outbox/saga để phối hợp các bước có trạng thái rõ và có thể phục hồi.
- Thiết kế business operation tự idempotent qua unique key hoặc conditional update.

### 5.3. Ví dụ cập nhật trạng thái booking

~~~sql
BEGIN;

INSERT INTO consumer_inbox (
    consumer_name, event_id, received_at, processed_at
)
VALUES (
    'inventory-projection', 'evt-booking-1842', CURRENT_TIMESTAMP, NULL
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Ứng dụng kiểm tra insert có thực sự tạo dòng mới.
-- Chỉ khi là event mới, thực hiện cập nhật projection.

UPDATE inventory_projection
SET confirmed_bookings = confirmed_bookings + 1
WHERE room_id = 'room-28';

UPDATE consumer_inbox
SET processed_at = CURRENT_TIMESTAMP
WHERE consumer_name = 'inventory-projection'
  AND event_id = 'evt-booking-1842';

COMMIT;
~~~

Đây là pseudo-example dùng cú pháp gần PostgreSQL; code thực tế cần lấy row count/RETURNING để biết insert mới hay conflict, và chỉ chạy UPDATE nếu event chưa xử lý. Không chạy UPDATE vô điều kiện như đoạn minh họa nếu muốn chống duplicate; phần kiểm tra đó thuộc logic ứng dụng hoặc một CTE/transaction cụ thể.

## 6. Idempotency key và business invariant

### 6.1. Message ID không đủ cho mọi nghiệp vụ

Giả sử client gửi yêu cầu phát hành invoice hai lần, producer tạo hai event:

- eventId = evt-A, orderId = order-123
- eventId = evt-B, orderId = order-123

Consumer deduplicate theo eventId vẫn xử lý cả hai. Nếu quy tắc nghiệp vụ là mỗi đơn chỉ có một invoice hiệu lực, cần **business key** như orderId + invoice type hoặc idempotency key đã thống nhất.

| ID/Key | Mục đích | Ví dụ |
| --- | --- | --- |
| eventId | Nhận diện một event cụ thể | evt-2026-0001 |
| correlationId | Nối các hoạt động cùng hành trình | corr-checkout-91 |
| causationId | Chỉ ra event/command đã gây ra event hiện tại | cmd-create-booking-42 |
| aggregateId | Định danh đối tượng nghiệp vụ | booking-123 |
| businessKey | Chống lặp một thao tác nghiệp vụ | invoice:order-123 |
| idempotencyKey | Nhận diện retry của cùng yêu cầu/tác vụ | client-request-9e2 |

Các trường này có thể liên hệ nhưng không thay thế nhau. Không sử dụng correlationId làm unique key nếu một hành trình tạo ra nhiều nghiệp vụ hợp lệ.

### 6.2. Unique constraint và conditional write

Ví dụ bảng invoice có ràng buộc một invoice type cho một order:

~~~sql
CREATE UNIQUE INDEX uq_invoice_order_type
ON invoices(order_id, invoice_type);
~~~

Khi hai worker cùng phát hành invoice, một transaction ghi trước; transaction kia gặp conflict và có thể đọc kết quả đã tồn tại. Đây là cách bảo vệ invariant ở nơi dữ liệu được lưu.

Với inventory, có thể dùng conditional update như chỉ giảm số lượng khi quantity còn đủ. Với chuyển tiền, cần ledger entry ID hoặc transaction key duy nhất; không dùng phép cộng số dư không kiểm soát.

**Idempotency nên phản ánh invariant của nghiệp vụ**, không chỉ là kỹ thuật lưu event ID.

## 7. Transactional outbox: tránh mất event sau khi ghi database

Một lỗi phổ biến là ứng dụng thực hiện:

1. Commit booking trong database.
2. Publish BookingCreated lên broker.

Nếu process chết giữa bước 1 và 2, booking tồn tại nhưng event không được phát. Nếu publish trước rồi database rollback, consumer có thể nhận event cho booking chưa tồn tại.

### 7.1. Mô hình outbox

Trong cùng transaction ghi booking, producer thêm một dòng vào bảng outbox:

~~~sql
BEGIN;

INSERT INTO bookings(id, status)
VALUES ('booking-123', 'CONFIRMED');

INSERT INTO outbox_events(
    event_id, aggregate_id, event_type, payload, created_at
)
VALUES (
    'evt-001',
    'booking-123',
    'BookingConfirmed',
    '{"bookingId":"booking-123"}',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Một relay đọc outbox chưa publish và gửi tới broker. Sau publisher confirm phù hợp, relay đánh dấu published hoặc lưu watermark. Nếu relay crash sau khi broker nhận event nhưng trước khi đánh dấu outbox, relay có thể publish lại. Vì vậy consumer vẫn cần idempotency.

~~~mermaid
flowchart LR
    APP["Command handler"] --> TX["DB transaction"]
    TX --> B[("Business state")]
    TX --> O[("Outbox table")]
    O --> RELAY["Outbox relay / CDC"]
    RELAY --> BROKER[("Event broker")]
    BROKER --> C["Consumers"]
    C --> INBOX[("Inbox + business state")]
~~~

Outbox giải quyết **atomicity giữa business state và ý định phát event** trong cùng database transaction. Nó không tự tạo exactly-once end-to-end vì publish/relay vẫn có thể lặp và consumer vẫn có thể xử lý lại.

### 7.2. Polling relay và CDC

- **Polling relay:** worker định kỳ truy vấn dòng outbox chưa publish, lấy theo batch và gửi. Cần index, lock/claim, quản lý trạng thái và dọn dữ liệu.
- **Change Data Capture (CDC):** đọc log thay đổi database để phát event. Có thể giảm polling nhưng cần quản lý connector, offsets, schema evolution, lag và phục hồi.
- **Managed integration:** dịch vụ cloud có thể hỗ trợ capture hoặc event routing; phải kiểm tra delivery semantics, retry, ordering và durability thực tế.

Không xóa outbox row ngay sau publish nếu cần audit hoặc replay. Retention và archive phải cân bằng dung lượng, chi phí và yêu cầu điều tra.

## 8. Consumer ACK/offset commit đúng thời điểm

Nguyên tắc tổng quát: **không ACK/commit tiến độ trước khi kết quả cần bảo vệ đã được commit bền vững**.

### 8.1. Message queue có visibility timeout

Với queue dùng visibility timeout:

1. Consumer nhận message; broker tạm ẩn message.
2. Consumer xử lý và commit business state.
3. Consumer xóa/ACK message.
4. Nếu xử lý vượt timeout, consumer gia hạn visibility nếu nền tảng hỗ trợ.
5. Nếu consumer chết, message xuất hiện lại sau lease.

Lease quá ngắn tạo duplicate; lease quá dài kéo dài thời gian phục hồi sau crash. Chọn timeout theo phân bố duration và có cơ chế gia hạn cho job dài. Lease không phải khóa độc quyền tuyệt đối nếu worker cũ vẫn chạy sau khi lease hết.

### 8.2. Log/partition và offset

Với broker dạng append-only log, consumer đọc record theo partition. Offset commit đánh dấu tiến độ; nếu commit sau side effect, restart có thể đọc lại record. Đây là mô hình at-least-once phổ biến.

Commit offset trước side effect giảm khả năng lặp nhưng có thể mất xử lý nếu crash. Chỉ dùng cách đó khi chấp nhận at-most-once hoặc có thể tái tạo từ nguồn khác.

### 8.3. Batch acknowledgement

Khi consumer xử lý một batch, một số record có thể thành công, một số lỗi. Cần xác định ACK theo từng message, theo batch hay theo contiguous offset. Với log có thứ tự, không commit offset vượt qua record chưa xử lý nếu muốn giữ semantics phù hợp. Cần kiểm thử lỗi ở giữa batch, partial success và replay.

## 9. Ordering: xử lý đúng thứ tự không phải mặc định

Event broker có thể đảm bảo thứ tự trong một phạm vi như partition, message group hoặc session, nhưng không nhất thiết toàn hệ thống.

Ví dụ hai sự kiện BookingCreated và BookingCancelled. Nếu Cancelled đến consumer trước Created, projection có thể tạo trạng thái cuối sai nếu không xét version và transition hợp lệ.

| Phạm vi | Đặc điểm | Trade-off |
| --- | --- | --- |
| Toàn topic/queue | Thứ tự toàn cục nếu dịch vụ hỗ trợ | Khó mở rộng song song, throughput thấp hơn |
| Theo partition/key | Thứ tự giữ trong một partition/key | Cần chọn partition key đúng; có thể hot partition |
| Theo entity/aggregate | Event của cùng booking giữ trình tự | Các entity khác nhau có thể chạy song song |
| Không đảm bảo thứ tự | Consumer chịu event đến bất kỳ thứ tự nào | Cần versioning, state machine và reconciliation |

### 9.1. Partition key

Chọn aggregateId làm partition key giúp event của cùng booking vào cùng partition trong mô hình hỗ trợ ordering theo partition. Nhưng partition key lệch có thể tạo hot partition. Tăng số partition có thể thay đổi mapping của key ở một số hệ thống và ảnh hưởng thứ tự nếu không thiết kế migration cẩn thận.

### 9.2. Version và optimistic concurrency

Mỗi aggregate có thể gắn version tăng dần:

~~~json
{
  "eventId": "evt-103",
  "aggregateId": "booking-123",
  "aggregateVersion": 7,
  "eventType": "BookingCancelled"
}
~~~

Consumer chỉ áp dụng event có version kế tiếp phù hợp; event cũ hoặc duplicate được bỏ qua, event có gap có thể được giữ lại hoặc yêu cầu reload state/replay. Quy tắc cụ thể phụ thuộc domain. Không chỉ dựa timestamp vì clock skew, event time và thứ tự commit có thể khác nhau.

## 10. Poison message, retry và DLQ

Poison message là message luôn thất bại do payload không hợp lệ, schema không hỗ trợ, dữ liệu thiếu hoặc bug xử lý. Retry liên tục không giúp nó thành công và có thể chặn cả partition hoặc làm queue backlog tăng.

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Transient | Timeout, HTTP 503, throttling tạm thời | Retry có backoff và jitter |
| Permanent data | Schema sai, field bắt buộc thiếu | DLQ, điều tra và sửa nguồn |
| Business rejection | Booking đã hủy, trạng thái không cho phép | Ghi kết quả nghiệp vụ hoặc bỏ qua có audit |
| Authorization | Credential hết hạn, thiếu quyền | Cảnh báo và khắc phục policy/secret |
| Dependency overload | DB pool hết, API downstream bão hòa | Backpressure, concurrency cap, retry giãn |
| Version mismatch | Consumer chưa hỗ trợ event schema mới | Compatibility policy, quarantine hoặc nâng cấp consumer |

### 10.1. Backoff và giới hạn retry

~~~text
delay(n) = min(maxDelay, baseDelay × 2^n) + randomJitter
~~~

Backoff có jitter giảm việc nhiều consumer retry cùng lúc. Cần giới hạn số lần thử, tổng thời gian, loại lỗi được retry và retention. Retry không được làm vượt hạn thanh toán hoặc deadline nghiệp vụ.

### 10.2. DLQ và replay có kiểm soát

DLQ cần giữ reason, eventId, correlationId, attempt, timestamp, consumer version và thông tin gốc đủ để điều tra. Payload nhạy cảm phải được bảo vệ.

Quy trình replay:

1. Phân loại lỗi và nguyên nhân gốc.
2. Xác định event đã từng tạo side effect chưa.
3. Sửa dữ liệu hoặc deploy consumer tương thích.
4. Kiểm tra idempotency/business key.
5. Replay theo batch nhỏ, giới hạn tốc độ.
6. Theo dõi kết quả và đối soát.
7. Ghi audit người thực hiện, phạm vi và kết quả.

Không tự động redrive toàn bộ DLQ ngay khi dependency vừa hồi phục; hành động đó có thể tạo burst thứ hai và làm hệ thống quá tải.

## 11. Exactly-once trong hệ thống stream

Một số stream processor/broker hỗ trợ transaction hoặc cơ chế exactly-once trong phạm vi đọc input, xử lý state và ghi output trong cùng hệ thống.

Ví dụ, framework có thể gắn output record với offset input trong transaction: hoặc cả output và tiến độ commit cùng thành công, hoặc cả hai không được xem là đã commit. Producer idempotent có thể ngăn retry publish tạo bản ghi trùng trong phạm vi broker hỗ trợ.

Những cơ chế này hữu ích cho stream processing, nhưng phải xác định giới hạn:

- Chỉ hỗ trợ một số broker, client, connector và phiên bản nhất định.
- Transaction có phạm vi trong broker/stream processor; gọi REST API ngoài không tự tham gia transaction.
- Ghi database bên ngoài cần transaction connector, sink semantics hoặc idempotency riêng.
- Exactly-once có thể yêu cầu cấu hình isolation, transaction ID, checkpoint và timeout đúng.
- Reprocessing từ nguồn ngoài hoặc side effect không có idempotency có thể tạo kết quả trùng.
- “Một lần” thường có nghĩa output được commit một lần trong logic được quản lý, không có nghĩa code chỉ chạy đúng một lần về vật lý.

### 11.1. Phân biệt processing và effect

Một record có thể được **đọc/xử lý lại** sau rollback hoặc recovery nhưng kết quả commit vẫn chỉ xuất hiện một lần trong transaction boundary. Cần phân biệt:

- **Execution count:** code được thực thi bao nhiêu lần.
- **Delivery count:** broker giao message bao nhiêu lần.
- **Committed output count:** số kết quả đã commit bền vững.
- **Business side effect count:** số tác dụng phụ bên ngoài thực sự xảy ra.

Exactly-once thường nhằm kiểm soát committed output hoặc state trong phạm vi cụ thể, không nhất thiết execution count bằng một.

## 12. External side effects: giới hạn quan trọng nhất

Giả sử consumer gọi API cổng thanh toán để trừ 500.000 đồng. Cổng thanh toán thực hiện thành công nhưng response bị mất. Consumer không biết kết quả và retry. Nếu API thanh toán không hỗ trợ idempotency key, khách hàng có thể bị trừ tiền hai lần.

### 12.1. Idempotency của downstream

Nếu external API hỗ trợ idempotency key, gửi cùng key cho mọi lần retry của cùng business operation. Downstream có thể trả lại kết quả cũ thay vì thực hiện side effect lần nữa.

Cần kiểm tra:

- Key có scope theo merchant/account hay toàn hệ thống?
- Key được giữ bao lâu?
- Payload khác nhưng cùng key thì trả lỗi hay dùng request đầu?
- Kết quả thất bại tạm thời có được lưu dưới key đó không?
- Có API tra cứu trạng thái theo key/transaction ID không?

Không giả định mọi API bên ngoài hỗ trợ semantics giống nhau. Đọc hợp đồng dịch vụ và kiểm thử lỗi sau khi side effect xảy ra nhưng trước response.

### 12.2. Nếu downstream không hỗ trợ idempotency

Có thể dùng trạng thái trung gian và reconciliation:

1. Lưu operation với business key duy nhất, trạng thái PENDING.
2. Gửi request tới downstream với reference ID có thể tra cứu.
3. Nếu nhận response xác nhận, đánh dấu SUCCEEDED.
4. Nếu timeout không rõ kết quả, đánh dấu UNKNOWN/PENDING_RECONCILIATION thay vì gửi lại mù quáng.
5. Query downstream hoặc đối soát theo statement/webhook.
6. Chỉ retry khi có căn cứ rằng thao tác trước chưa xảy ra.

Hệ thống phân tán đôi khi phải chấp nhận trạng thái **kết quả chưa xác định** cho tới khi đối soát xong. Đó an toàn hơn việc giả định timeout nghĩa là thất bại.

### 12.3. Saga và compensation

Trong quy trình nhiều bước, Saga cho phép mỗi bước ghi nhận trạng thái và bước bù xử lý khi quy trình thất bại. Ví dụ giữ chỗ thành công nhưng thanh toán thất bại thì hủy reservation. Compensation là **một nghiệp vụ mới** có tác dụng khôi phục gần tương đương, không phải rollback vật lý của transaction đã commit.

Saga vẫn cần idempotency, retry, ordering, timeout và đối soát. Không dùng từ exactly-once để che giấu trạng thái trung gian hoặc bước bù chưa hoàn tất.

## 13. Kiến trúc tham khảo: Outbox + At-least-once + Idempotent consumer

Đối với event nghiệp vụ quan trọng, một cấu trúc dễ kiểm soát là:

~~~mermaid
flowchart TB
    CMD["Command/API"] --> TX["Transaction"]
    TX --> AGG[("Business state")]
    TX --> OB[("Outbox")]
    OB --> RELAY["Publisher relay"]
    RELAY --> BROKER[("At-least-once broker")]
    BROKER --> C1["Consumer A"]
    BROKER --> C2["Consumer B"]
    C1 --> TX1["DB transaction"]
    TX1 --> I1[("Inbox + state A")]
    C2 --> TX2["DB transaction"]
    TX2 --> I2[("Inbox + state B")]
~~~

Các đặc tính:

- Business state và outbox event được commit cùng transaction nguồn.
- Relay có thể publish lại khi không chắc publish trước đó thành công.
- Consumer deduplicate theo event ID và/hoặc business key.
- Inbox record và business state của consumer commit cùng transaction nếu nằm trong cùng DB.
- Side effect ngoài DB dùng idempotency key, trạng thái trung gian hoặc reconciliation.
- DLQ và replay có kiểm soát.
- Monitoring phân biệt publish, delivery, processing và business completion.

Đây không phải cách triển khai duy nhất. Với hệ thống log, transaction broker và stream processor có thể phù hợp hơn; với tác vụ đơn giản, queue managed và conditional write có thể đủ. Chọn công cụ theo semantics và mức phức tạp cần bảo vệ.

## 14. Sơ đồ lỗi theo điểm crash

| Điểm xảy ra lỗi | Nguy cơ | Cơ chế giảm rủi ro |
| --- | --- | --- |
| Trước khi producer lưu event | Event chưa tồn tại | Retry command có idempotency/business key |
| Sau DB commit, trước publish | Mất event nếu không có outbox | Transactional outbox/CDC |
| Sau broker persist, trước publisher ACK | Producer publish lại | Idempotent producer hoặc consumer dedup |
| Sau consumer receive, trước side effect | Message giao lại | Retry/visibility policy |
| Sau side effect, trước ACK | Duplicate side effect | Inbox/unique key/downstream idempotency |
| Sau ACK, trước side effect | Mất tác dụng phụ | ACK sau commit bền vững |
| Sau DB update, trước checkpoint/offset commit | Record đọc lại | Transactional output/offset hoặc idempotent write |
| Trong batch processing | Partial completion | Checkpoint và chunk idempotency |
| Khi replay DLQ | Side effect đã từng xảy ra | Business key, audit và controlled replay |
| Khi event đến sai thứ tự | State transition sai | Aggregate version, ordering key, reconciliation |

Không một cơ chế đơn lẻ bảo vệ tất cả các dòng. Thiết kế cần kết hợp transaction boundary, durable state, retry policy và đối soát.

## 15. Ordering, concurrency và partition trong cloud

Tăng số consumer có thể tăng throughput, nhưng cũng tăng khả năng xử lý đồng thời. Nếu hai event của cùng aggregate chạy song song, thứ tự nghiệp vụ có thể bị phá dù broker giao theo đúng thứ tự.

Các lựa chọn:

- Partition theo aggregate key để event cùng entity đi cùng partition.
- Chỉ cho một consumer xử lý mỗi partition tại một thời điểm theo semantics broker.
- Dùng version check/optimistic concurrency tại DB.
- Với work queue, dùng message group/session key nếu dịch vụ hỗ trợ ordering theo group.
- Với thao tác phụ thuộc thứ tự, chỉ ACK event sau khi state transition hợp lệ.
- Với event đến muộn, lưu quarantine/retry hoặc reload state theo quy tắc domain.

### 15.1. Hot key và trade-off

Nếu 40% traffic thuộc một tenant hoặc aggregate key duy nhất, partition theo key có thể làm một partition nóng trong khi các partition khác rảnh. Tăng worker không khắc phục được nếu partition đó chỉ có một luồng xử lý tuần tự.

Có thể chia nhỏ key nếu nghiệp vụ cho phép, nhưng nếu cần ordering toàn aggregate thì không được tùy tiện tách. Đôi khi throughput thấp hơn là cái giá phải trả để bảo vệ invariant.

## 16. Quan sát và vận hành delivery semantics

### 16.1. Đo từng giai đoạn

| Chỉ số | Ý nghĩa |
| --- | --- |
| Publish success/failure | Producer có thể gửi event tới broker không? |
| Publish confirm latency | Thời gian broker xác nhận publish |
| Consumer delivery count | Số lần message được giao |
| Redelivery/duplicate rate | Mức giao lại hoặc nhận diện trùng |
| Consumer processing duration | Thời gian xử lý mỗi event |
| ACK/offset commit lag | Độ trễ xác nhận tiến độ |
| Consumer lag / oldest message age | Backlog và độ trễ chưa xử lý |
| Retry count và DLQ depth | Lỗi kéo dài/poison message |
| Outbox backlog age | Event chưa được relay |
| Inbox dedup hit | Số event bị loại do đã xử lý |
| Business completion rate | Số nghiệp vụ thực sự hoàn tất |
| Reconciliation mismatch | Sai lệch giữa nguồn và downstream |

Đừng chỉ xem queue depth. Queue có thể cạn trong khi consumer ACK quá sớm và làm mất side effect; hoặc broker không backlog nhưng nghiệp vụ vẫn chưa đối soát. Kết hợp metric kỹ thuật với business metric.

### 16.2. Log và trace

Event nên mang eventId, aggregateId, aggregateVersion, correlationId, causationId, eventType, occurredAt và schemaVersion khi phù hợp.

Log không nên chứa payload nhạy cảm đầy đủ. Trace context có thể đi qua message metadata để nối span producer-consumer; correlation ID nghiệp vụ vẫn hữu ích khi trace sampling không giữ lại span.

Giám sát thêm consumer version, schema version, deployment ID, partition, retry attempt và lý do DLQ để điều tra lỗi sau khi nâng cấp.

### 16.3. Cảnh báo theo tác động

- Outbox event chưa được publish quá ngưỡng thời gian.
- Oldest message age vượt SLO xử lý.
- Duplicate/redelivery rate tăng đột ngột.
- Consumer lag tăng dù worker CPU thấp.
- DLQ xuất hiện event của luồng thanh toán/booking.
- Reconciliation mismatch tăng.
- External operation ở trạng thái UNKNOWN quá thời hạn.
- Một partition bị hot key hoặc consumer rebalance liên tục.

Mỗi alert cần owner, dashboard và runbook cụ thể. Không nên cảnh báo mọi duplicate nếu consumer đã deduplicate an toàn và tỷ lệ nằm trong baseline; thay đổi bất thường vẫn cần được điều tra.

## 17. Kịch bản chất lượng và tiêu chí đo

Các ngưỡng sau là **ví dụ minh họa**. Khi áp dụng cần xác định event hợp lệ, điểm đo, cửa sổ thời gian, workload và loại lỗi.

| Mã | Tình huống | Phản hồi kỳ vọng | Thước đo minh họa |
| --- | --- | --- | --- |
| QA-EVT-01 | Producer chết sau DB commit nhưng trước publish | Event vẫn được relay từ outbox | 100% business state có outbox tương ứng; 99,9% event hợp lệ được publish trong 60 giây |
| QA-EVT-02 | Consumer chết sau side effect trước ACK | Message giao lại nhưng nghiệp vụ không bị lặp | Không có invoice/booking/payment duplicate trong bộ kiểm thử |
| QA-EVT-03 | Event cùng aggregate đến cạnh tranh hoặc sai thứ tự | State transition hợp lệ theo version/domain rule | Không áp dụng event version cũ; event gap được xử lý theo policy |
| QA-EVT-04 | External payment timeout sau khi cổng đã xử lý | Hệ thống tra cứu/đối soát trạng thái trước retry | Không có charge trùng trong bộ test fault injection |
| QA-EVT-05 | Poison message không thể xử lý | Đưa DLQ và tiếp tục xử lý event khác theo policy | Message lỗi không chặn queue quá ngưỡng; có alert và audit |
| QA-EVT-06 | Replay một tập event đã xử lý | Projection khôi phục nhưng side effect nghiệp vụ không nhân đôi | Business key duy nhất; số kết quả sau replay khớp snapshot |

Kịch bản phải trả lời: nguồn tác động nào, sự kiện gì, môi trường nào, thành phần nào chịu ảnh hưởng, phản hồi ra sao và đo thế nào. “Không duplicate” cần định nghĩa theo invoice ID, order ID hay charge ID để có thể kiểm thử nhất quán.

## 18. Kiểm thử fault injection và recovery

Một bài test có giá trị nên chủ động tạo lỗi tại đúng ranh giới cần xác minh.

### 18.1. Các trường hợp nên thử

1. Producer timeout ngay sau publish để kiểm tra retry và duplicate publish.
2. Broker persist event nhưng publisher không nhận confirm.
3. Consumer process kill ngay trước side effect.
4. Consumer kill ngay sau DB commit nhưng trước ACK.
5. Làm cho ACK/offset commit thất bại.
6. Kéo dài xử lý vượt visibility timeout.
7. Restart consumer trong lúc rebalance.
8. Replay message từ DLQ/offset cũ.
9. Gửi event cùng aggregate sai thứ tự.
10. Downstream side effect thành công nhưng response bị mất.
11. Thay đổi schema event khi consumer phiên bản cũ vẫn chạy.
12. Làm đầy queue hoặc chạm quota để kiểm tra backpressure.

### 18.2. Bằng chứng cần lưu

- Event ID, business key, correlation ID và version.
- Thời điểm publish, broker confirm, deliver, side effect commit và ACK/offset commit.
- Số lần delivery/attempt.
- Số bản ghi nghiệp vụ được tạo/cập nhật.
- Duplicate được nhận diện bao nhiêu lần.
- DLQ, replay và reconciliation result.
- Queue age, consumer lag, p95/p99 và chi phí thử nghiệm.

Không dùng một lần test thành công làm bằng chứng cho mọi kiểu lỗi. Lặp lại test ở nhiều điểm crash và với concurrency đại diện.

## 19. Chi phí và tác động của ngữ nghĩa giao nhận

Ngữ nghĩa mạnh hơn có thể kéo theo chi phí vận hành và hạ tầng:

- Broker durability, replication và retention.
- Transaction/checkpoint state và metadata.
- Inbox/outbox table, index, cleanup và storage.
- Deduplication lookup, conditional writes và transaction contention.
- Retry, duplicate delivery, DLQ và replay.
- Reconciliation jobs và vận hành ngoại lệ.
- Tracing/logging/audit và lưu giữ dữ liệu.
- Throughput giảm khi yêu cầu ordering hoặc transaction rộng hơn.

Không nên chọn exactly-once ở mọi tầng vì nghe an toàn. Hãy chọn mức bảo đảm cần thiết cho từng loại event. Telemetry có thể chấp nhận at-most-once; event đặt phòng có thể cần at-least-once + idempotent consumer; stream aggregation có thể cần exactly-once trong transaction boundary của processor; payment API cần idempotency key và reconciliation.

### 19.1. Cost per successfully applied event

~~~text
Cost per successfully applied event
  = (Broker + compute + database + network
     + observability + retry/DLQ + reconciliation cost)
    / Number of business events applied correctly
~~~

Mẫu số không phải số message được giao. Event có thể giao ba lần nhưng chỉ áp dụng một lần hợp lệ; hoặc được ACK nhưng nghiệp vụ chưa cập nhật. Chỉ số kinh tế phải dựa trên **business effect đúng**.

## 20. Case study: xác nhận booking và phát hành hóa đơn

### 20.1. Bối cảnh

Một nền tảng đặt phòng dùng Java/Spring Boot, PostgreSQL và message broker managed. Khi booking được xác nhận, hệ thống phát event cho ba consumer:

- Inventory projection cập nhật số lượng đã đặt.
- Notification worker gửi email.
- Billing worker phát hành hóa đơn.

Yêu cầu giả định:

- Không tạo booking hoặc invoice trùng.
- Event hợp lệ được consumer tiếp nhận trong vòng 30 giây ở tải mục tiêu.
- Khi worker chết sau commit nhưng trước ACK, event được giao lại và không tạo side effect trùng.
- Sai lệch payment/invoice được phát hiện và xử lý đối soát.
- Event cũ có thể replay để dựng lại projection mà không gửi email hoặc phát hành hóa đơn lần hai.

### 20.2. Quyết định thiết kế

**Producer:** API commit booking và outbox row trong cùng transaction. Relay publish theo at-least-once; publisher confirm được ghi nhận theo broker semantics. Nếu relay crash sau publish, event có thể được gửi lại.

**Inventory consumer:** Inbox + business update cùng database transaction; version của booking dùng để phát hiện event cũ hoặc gap.

**Notification consumer:** Ghi notification intent với unique business key; gọi email provider với idempotency key nếu được hỗ trợ. Nếu timeout không rõ trạng thái, lưu UNKNOWN và reconciliation trước khi gửi lại khi cần.

**Billing consumer:** Mỗi invoice có unique key theo booking và loại hóa đơn. Invoice state được lưu trước/đi cùng luồng phát hành; external billing provider được gọi bằng idempotency key/reference có thể tra cứu.

**Replay:** Replay event dùng cùng eventId và business key; projection có thể được rebuild trong chế độ riêng, còn side effect email/billing được tắt hoặc chỉ chạy khi replay policy cho phép.

~~~mermaid
flowchart TB
    API["Booking API"] --> TX["DB transaction"]
    TX --> B[("Booking")]
    TX --> O[("Outbox")]
    O --> R["Relay"]
    R --> Q[("Broker")]
    Q --> I["Inventory consumer"]
    Q --> N["Notification consumer"]
    Q --> BILL["Billing consumer"]
    I --> IDB[("Inbox + Inventory projection")]
    N --> NDB[("Notification intent")]
    N --> EMAIL["Email provider"]
    BILL --> BDB[("Invoice state + unique key")]
    BDB --> PAY["Billing provider"]
~~~

### 20.3. Lỗi và cách xử lý

| Lỗi | Hành vi |
| --- | --- |
| Relay publish xong nhưng chưa đánh dấu outbox | Publish lại; consumer deduplicate |
| Inventory worker chết sau DB commit | Event được giao lại; inbox xác định đã xử lý |
| Email timeout không rõ đã gửi chưa | Tra cứu provider nếu có; dùng idempotency; reconciliation |
| Billing event đến hai lần với event ID khác | Unique business key ngăn invoice thứ hai |
| Event version 5 đến trước version 4 | Consumer áp dụng version policy, không ghi lùi state |
| Replay toàn bộ event lịch sử | Rebuild projection tách khỏi external side effects |

### 20.4. Đánh giá

Không tuyên bố “hệ thống exactly-once toàn phần”. Hệ thống dùng at-least-once delivery, durable outbox, inbox, unique business keys, idempotent side effect nơi hỗ trợ và reconciliation cho kết quả không rõ. Điều đó tạo ra **bảo đảm nghiệp vụ đo được** dù code/consumer có thể thực thi hoặc nhận event nhiều hơn một lần.

## 21. Checklist thiết kế

- [ ] Đã xác định semantics của publish, broker persist, delivery, ACK/offset và business completion.
- [ ] Đã chọn at-most-once, at-least-once hoặc exactly-once trong đúng phạm vi.
- [ ] Có event ID, aggregate ID/version, correlation ID và business key khi cần.
- [ ] Producer retry không vô tình tạo business operation trùng.
- [ ] Business state và event được ghi nhất quán qua outbox/CDC hoặc cơ chế tương đương.
- [ ] Consumer dùng inbox/dedup và unique constraint/conditional write.
- [ ] Inbox và business state cùng transaction khi cần atomicity.
- [ ] Side effect ngoài có idempotency key hoặc trạng thái UNKNOWN/reconciliation.
- [ ] ACK/offset commit diễn ra sau khi kết quả cần bảo vệ đã bền vững.
- [ ] Visibility timeout/lease, heartbeat và graceful shutdown phù hợp duration.
- [ ] Ordering và partition key phản ánh invariant nghiệp vụ.
- [ ] Retry có phân loại lỗi, backoff, giới hạn, DLQ và replay có audit.
- [ ] Schema evolution, consumer version và compatibility được kiểm thử.
- [ ] Có metrics publish/delivery/duplicate/lag/business completion.
- [ ] Đã fault-inject tại các điểm crash trước/sau side effect và ACK.
- [ ] Có reconciliation và bằng chứng đạt/trượt theo SLO.
- [ ] TCO gồm broker, state store, duplicate/retry, log/trace và vận hành.

## 22. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review semantics sự kiện |
| --- | --- |
| **Operational Excellence** | Có thể truy vết event, điều tra duplicate, replay có kiểm soát và phục hồi consumer không? |
| **Security** | Event có dữ liệu tối thiểu, xác minh producer/consumer, tenant isolation và bảo vệ DLQ không? |
| **Reliability** | Publish, delivery, ACK, checkpoint, idempotency và reconciliation chịu được lỗi ở các điểm nào? |
| **Performance Efficiency** | Ordering, transaction, dedup lookup và concurrency ảnh hưởng throughput/p95 ra sao? |
| **Cost Optimization** | Chi phí durability, retention, inbox/outbox, retry, trace và reconciliation trên event thành công là bao nhiêu? |
| **Sustainability** | Có giảm replay/duplicate không cần thiết, lưu trữ thừa và xử lý lặp không? |

**Kết luận:** At-most-once giảm khả năng lặp nhưng chấp nhận nguy cơ bỏ sót; at-least-once giảm nguy cơ mất message bằng cách cho phép giao lại; exactly-once chỉ có ý nghĩa khi nêu rõ phạm vi transaction và kết quả được bảo đảm. Đối với hệ thống nghiệp vụ quan trọng, nền tảng thực tế thường là **at-least-once + idempotency + durable state + reconciliation**, kết hợp các giao dịch exactly-once ở phạm vi broker/processor khi phù hợp. Hãy đo kết quả nghiệp vụ cuối cùng và kiểm thử các điểm crash thay vì dựa vào nhãn semantics của một dịch vụ riêng lẻ.
