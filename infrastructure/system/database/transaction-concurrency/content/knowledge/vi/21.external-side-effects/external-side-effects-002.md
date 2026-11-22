# Rủi ro gọi dịch vụ ngoài trước hoặc sau COMMIT

Một transaction database có thể cập nhật nhiều bảng và commit chúng như một đơn vị nguyên tử. Nhưng khi nghiệp vụ còn phải gọi API bên ngoài, gửi email, phát message hoặc yêu cầu một hệ thống khác thực hiện tác vụ, ranh giới nguyên tử của database không tự mở rộng sang hệ thống đó.

Thời điểm gọi dịch vụ ngoài tạo ra hai nhóm rủi ro:

- **Gọi trước `COMMIT`:** dịch vụ ngoài có thể đã thực hiện tác dụng phụ trong khi transaction database sau đó rollback. Hệ thống bên ngoài đã thay đổi nhưng database không ghi nhận thay đổi tương ứng.
- **Gọi sau `COMMIT`:** database đã lưu thành công nhưng tiến trình có thể chết hoặc lời gọi dịch vụ ngoài thất bại trước khi thông báo được gửi. Database đã đổi trạng thái nhưng hệ thống ngoài chưa biết.

Đây là bài toán dual-write: một nghiệp vụ cần ghi vào hai hệ thống độc lập nhưng không có một transaction nguyên tử chung. Muốn xử lý đúng, cần xác định rõ điều gì phải được commit cùng nhau, cách gửi lại khi lỗi, cách chống xử lý trùng và cách phục hồi khi kết quả của một lời gọi không rõ ràng.

## 1. Ranh giới của transaction database

Giả sử ứng dụng tạo đơn hàng. Trong database, nó cần ghi:

- Một dòng `orders` với trạng thái `CREATED`.
- Các dòng `order_item`.
- Một bản ghi thanh toán hoặc yêu cầu thanh toán.

Sau đó ứng dụng cần gọi dịch vụ vận chuyển để tạo nhãn giao hàng hoặc gọi dịch vụ thanh toán để thu tiền. Database chỉ có thể bảo đảm tính nguyên tử cho các thay đổi nằm trong transaction do chính nó quản lý. Nó không thể tự rollback một email đã gửi, một khoản tiền đã bị cổng thanh toán thu hoặc một lệnh đã được hệ thống vận chuyển chấp nhận.

```text
Database transaction:
  BEGIN
    INSERT orders
    INSERT order_items
    UPDATE inventory
  COMMIT

External systems:
  Payment API
  Shipping API
  Email provider
  Message broker
```

Nếu ứng dụng gọi một dịch vụ bên ngoài giữa `BEGIN` và `COMMIT`, hai hệ thống có thể kết thúc ở hai trạng thái khác nhau. Nếu gọi sau `COMMIT`, vẫn có khoảng thời gian giữa lúc database commit và lúc dịch vụ ngoài nhận thông báo.

Một lời gọi HTTP thành công cũng không đồng nghĩa toàn bộ nghiệp vụ đã hoàn tất. Nó chỉ cho biết phía server trả về một kết quả theo giao thức của API. Ứng dụng còn phải hiểu trạng thái nghiệp vụ, timeout, retry, phản hồi lặp và khả năng tra cứu kết quả sau khi mất kết nối.

## 2. Rủi ro khi gọi dịch vụ ngoài trước COMMIT

Mẫu xử lý dễ mắc lỗi:

```text
BEGIN
  cập nhật dữ liệu đơn hàng
  gọi Payment API để thu tiền
  ghi nhận payment_id vào database
COMMIT
```

Giả sử Payment API đã thu tiền thành công nhưng câu `COMMIT` database thất bại do deadlock, lỗi constraint, mất kết nối hoặc tiến trình bị dừng. Payment service vẫn giữ giao dịch thu tiền, trong khi database có thể rollback toàn bộ thay đổi của ứng dụng.

### 2.1. Tác dụng phụ đã xảy ra nhưng transaction rollback

Ví dụ:

```text
T1: BEGIN
T1: UPDATE orders SET status = 'PAYMENT_PENDING'
T1: gọi Payment API -> thu 500.000 đồng thành công
T1: INSERT payment_record -> lỗi
T1: ROLLBACK

Kết quả:
  Database: đơn hàng chưa có payment_record đã commit
  Payment: 500.000 đồng đã bị thu
```

Database rollback không thể tự hoàn tiền tại Payment API. Ứng dụng phải có một thao tác bù trừ hoặc quy trình đối soát để tìm và xử lý khoản thu đã thành công.

### 2.2. Giao dịch bên ngoài nhìn thấy một ý định chưa được xác nhận

Trong khi transaction database chưa commit, trạng thái nghiệp vụ mới có thể chưa được các transaction khác nhìn thấy. Tuy nhiên, dịch vụ ngoài đã nhận yêu cầu và có thể thực hiện tác dụng phụ ngay. Nếu database rollback, hệ thống ngoài vẫn hành động dựa trên một ý định không còn tồn tại trong trạng thái đã commit của database.

Điều này đặc biệt nguy hiểm khi dịch vụ ngoài gửi callback hoặc webhook ngược về ứng dụng trước khi transaction gốc commit. Callback có thể không tìm thấy bản ghi tương ứng hoặc đọc thấy trạng thái cũ. Việc xử lý callback cần có trạng thái chờ, retry hoặc cơ chế tương quan để không phụ thuộc vào một transaction đang mở.

### 2.3. Giữ khóa database trong lúc chờ mạng

Lời gọi mạng có độ trễ khó dự đoán. Payment API có thể phản hồi trong vài chục mili giây, nhưng cũng có thể mất vài giây hoặc timeout. Nếu gọi nó khi transaction vẫn đang giữ row lock hoặc range lock:

- Các transaction khác phải chờ lâu hơn để cập nhật cùng dữ liệu.
- Lock wait và deadlock có thể tăng.
- Connection và transaction resource bị chiếm dụng trong lúc ứng dụng không thực hiện SQL.
- Khi dịch vụ ngoài chậm, throughput database có thể giảm mạnh.
- Timeout của HTTP và timeout của transaction có thể không đồng bộ; ứng dụng có thể rollback trong khi dịch vụ ngoài vẫn đang xử lý.

Một transaction database nên bao quanh phần đọc/ghi cần tính nguyên tử trong database. Không nên giữ transaction mở chỉ để đợi một dịch vụ độc lập phản hồi, trừ khi đang sử dụng một giao thức phân tán được thiết kế rõ ràng cho việc đó.

### 2.4. Timeout không cho biết dịch vụ ngoài đã làm gì

Nếu client timeout khi gọi Payment API, có ít nhất hai khả năng:

1. Request chưa đến server hoặc server chưa thực hiện tác dụng phụ.
2. Server đã thu tiền nhưng response bị mất hoặc đến quá muộn.

Nếu ứng dụng coi mọi timeout là thất bại chắc chắn, nó có thể không ghi nhận một khoản thu đã xảy ra. Nếu retry bằng một request mới, nó có thể thu tiền hai lần. Cần idempotency key ổn định và API tra cứu trạng thái theo key hoặc transaction ID để giải quyết kết quả không rõ ràng.

## 3. Rủi ro khi gọi dịch vụ ngoài sau COMMIT

Gọi sau commit giúp database hoàn tất transaction trước khi ứng dụng thực hiện tác dụng phụ. Tuy nhiên, mẫu đơn giản sau vẫn có một khoảng lỗi:

```text
BEGIN
  INSERT order
  UPDATE inventory
COMMIT

gọi Shipping API để tạo shipment
```

Database đã commit, nhưng tiến trình có thể dừng sau `COMMIT` và trước lời gọi Shipping API. Đơn hàng tồn tại và tồn kho đã giảm, nhưng shipment chưa được tạo.

### 3.1. Tiến trình chết giữa COMMIT và lời gọi ngoài

```text
1. Database commit order thành công.
2. Process bị kill hoặc máy chủ restart.
3. Lệnh gọi Shipping API chưa được gửi.
4. Không có transaction database nào rollback được order đã commit.
```

Nếu ứng dụng chỉ dựa vào một callback `afterCommit` trong bộ nhớ để gọi API, callback đó có thể bị mất khi process chết. Callback chạy sau commit giúp tránh tác dụng phụ trước commit, nhưng không tự tạo một công việc bền vững để chạy lại sau restart.

### 3.2. Dịch vụ ngoài lỗi sau khi database đã commit

Ngay cả khi process còn sống, Shipping API có thể trả lỗi 503, timeout, từ chối request hoặc tạm ngừng hoạt động. Lúc đó database đã có đơn hàng nhưng hệ thống chưa có shipment. Nếu không lưu trạng thái cần xử lý lại, ứng dụng có thể bỏ sót công việc.

Nên mô hình hóa trạng thái rõ ràng, ví dụ:

| Trạng thái đơn hàng | Trạng thái shipment | Ý nghĩa |
|---|---|---|
| `CREATED` | `PENDING` | Đơn đã commit, yêu cầu tạo shipment đang chờ gửi |
| `CREATED` | `SUBMITTED` | Đã gửi yêu cầu và đang chờ kết quả |
| `CREATED` | `CONFIRMED` | Dịch vụ vận chuyển xác nhận shipment |
| `CREATED` | `RETRY` | Lần gửi thất bại tạm thời, cần thử lại |
| `CANCELLED` | `NOT_REQUIRED` | Đơn bị hủy theo quy tắc nghiệp vụ |

Trạng thái `PENDING` phải được lưu bền vững trong database. Một worker có thể tìm các công việc đang chờ và gửi lại sau khi hệ thống phục hồi.

### 3.3. Dịch vụ ngoài đã thành công nhưng response bị mất

Sau commit, ứng dụng gọi dịch vụ ngoài. Server thực hiện thành công nhưng response bị mất. Ứng dụng không biết request đã thành công hay chưa và có thể gửi lại.

```text
Ứng dụng -> Shipping API: create shipment
Shipping API: tạo shipment S-100 thành công
Shipping API -> Ứng dụng: response bị mất
Ứng dụng: timeout, retry
Shipping API: có thể tạo shipment S-101 nếu không chống trùng
```

Nếu API không hỗ trợ idempotency hoặc tra cứu theo mã yêu cầu, retry có thể tạo nhiều shipment cho cùng một đơn hàng. Gửi sau commit giải quyết rủi ro rollback database sau tác dụng phụ, nhưng vẫn cần xử lý delivery lặp và kết quả không rõ ràng.

## 4. So sánh gọi trước và sau COMMIT

| Thời điểm gọi | Rủi ro chính | Hậu quả có thể xảy ra |
|---|---|---|
| Trước COMMIT | Dịch vụ ngoài thành công, transaction database rollback | Tác dụng phụ bên ngoài không có bản ghi database tương ứng |
| Trước COMMIT | Giữ khóa trong lúc chờ mạng | Lock wait, deadlock, connection bị chiếm lâu |
| Trước COMMIT | Timeout không rõ kết quả | Retry có thể tạo tác dụng phụ trùng; rollback có thể không đảo ngược tác dụng phụ |
| Sau COMMIT | Process chết trước khi gọi dịch vụ ngoài | Database đã đổi nhưng dịch vụ ngoài chưa được thông báo |
| Sau COMMIT | Dịch vụ ngoài lỗi tạm thời | Công việc cần được lưu và retry bền vững |
| Sau COMMIT | Response mất sau khi dịch vụ ngoài đã thành công | Retry có thể thực hiện tác dụng phụ lần thứ hai |
| Sau COMMIT | Callback chạy trong bộ nhớ bị mất khi restart | Không có cơ chế tự khôi phục công việc đã commit |

Không có thứ tự gọi đơn giản nào tự tạo transaction nguyên tử xuyên hai hệ thống. Cần một thiết kế ghi nhận ý định bền vững, gửi lại an toàn và xử lý kết quả lặp.

## 5. Transactional outbox: ghi ý định gửi cùng transaction

**Transactional outbox** giải quyết khoảng trống giữa database commit và việc gửi thông báo. Ứng dụng ghi dữ liệu nghiệp vụ và một bản ghi outbox trong cùng transaction database. Một worker riêng đọc outbox rồi gửi thông báo đến broker hoặc dịch vụ ngoài.

Nếu transaction rollback, cả dữ liệu nghiệp vụ và outbox record đều rollback. Nếu transaction commit, cả hai đều tồn tại. Vì vậy, dù process chết ngay sau commit, worker vẫn có thể tìm thấy outbox record để tiếp tục gửi.

```text
Ứng dụng
   |
   v
BEGIN DATABASE TRANSACTION
   - tạo order
   - cập nhật inventory
   - INSERT outbox_event
COMMIT
   |
   v
Outbox worker đọc event đã commit
   |
   v
Gửi event đến broker / external API
   |
   v
Đánh dấu event đã gửi hoặc lưu trạng thái retry
```

### 5.1. Schema outbox minh họa

```sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(100) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(120) NOT NULL,
    aggregate_seq  BIGINT,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP,
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    last_error     TEXT
);

CREATE INDEX ix_outbox_pending
    ON outbox_event (published_at, next_attempt_at, created_at);
```

Các cột và kiểu dữ liệu là ví dụ tổng quát; hệ thống thực tế có thể thêm `status`, `locked_until`, `worker_id`, partition key hoặc dùng kiểu JSON. `event_id` là định danh ổn định để consumer chống xử lý lặp. `aggregate_id` xác định đối tượng nghiệp vụ; `aggregate_seq` có thể dùng để duy trì thứ tự sự kiện của cùng aggregate.

### 5.2. Ghi outbox cùng dữ liệu nghiệp vụ

```sql
BEGIN;

INSERT INTO orders (order_id, customer_id, status, created_at)
VALUES (:order_id, :customer_id, 'CREATED', CURRENT_TIMESTAMP);

UPDATE inventory
SET available_qty = available_qty - :quantity
WHERE product_id = :product_id
  AND available_qty >= :quantity;

-- Ứng dụng kiểm tra số dòng cập nhật đúng 1; nếu không thì ROLLBACK.

INSERT INTO outbox_event (
    event_id, aggregate_type, aggregate_id,
    event_type, aggregate_seq, payload, created_at
)
VALUES (
    :event_id, 'Order', :order_id,
    'OrderCreated', :sequence, :payload, CURRENT_TIMESTAMP
);

COMMIT;
```

Lệnh ghi outbox nằm trong cùng transaction với `orders` và `inventory`. Nếu cập nhật tồn kho thất bại, transaction rollback nên không có event `OrderCreated` bị phát nhầm. Nếu commit thành công, outbox record bền vững và có thể được worker xử lý sau.

### 5.3. Worker gửi event

Worker có thể lấy các event chưa gửi, gửi đến broker rồi đánh dấu đã gửi. Pseudocode:

```text
loop:
    events = claim_pending_events(batch_size)

    for event in events:
        try:
            publish(event.event_id, event.payload)
            mark_published(event.event_id)
        catch transient_error:
            schedule_retry(event.event_id, backoff)
```

Việc claim event phải an toàn khi có nhiều worker. Có thể dùng row lock như `FOR UPDATE SKIP LOCKED`, lease trên từng event hoặc cơ chế claim nguyên tử phù hợp với DBMS. Không nên để hai worker cùng xử lý một dòng pending mà không có điều phối.

Quan trọng: gửi event và đánh dấu `published_at` thường không nằm trong cùng transaction nguyên tử với broker. Nếu broker đã nhận event nhưng worker chết trước khi đánh dấu published, worker khác sẽ gửi lại event. Vì vậy, transactional outbox thường cung cấp **at-least-once delivery**; consumer phải idempotent.

## 6. Vì sao outbox vẫn có thể gửi trùng?

Xem trình tự:

```text
1. Worker đọc event E-10.
2. Worker publish E-10 đến broker.
3. Broker xác nhận đã nhận.
4. Worker bị crash trước khi cập nhật published_at.
5. Worker mới đọc E-10 vì nó vẫn được xem là pending.
6. Worker mới publish E-10 lần nữa.
```

Không có lỗi trong transaction nghiệp vụ: order và outbox đã commit đúng. Việc gửi trùng phát sinh vì database và broker không cùng tham gia một commit nguyên tử. Thay vì cố loại bỏ mọi khả năng gửi trùng, hệ thống thường thiết kế consumer xử lý lặp an toàn.

Nếu broker hỗ trợ producer idempotence hoặc transaction, tính năng đó có thể giảm duplicate trong phạm vi broker và producer session. Tuy nhiên, nó không tự làm cho tác dụng phụ ở database hoặc dịch vụ downstream trở thành exactly-once end-to-end.

## 7. Inbox và idempotent consumer

Consumer nên lưu event ID đã xử lý bằng một unique constraint. Việc ghi nhận event và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction của consumer.

```sql
CREATE TABLE inbox_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(100) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Luồng xử lý:

```text
BEGIN CONSUMER TRANSACTION
  thử INSERT inbox_message(consumer_name, event_id)

  nếu insert thành công:
      áp dụng thay đổi nghiệp vụ
      COMMIT
      ACK message

  nếu event_id đã tồn tại:
      không áp dụng tác dụng phụ lần nữa
      COMMIT / kết thúc xử lý
      ACK message
```

Ví dụ PostgreSQL:

```sql
BEGIN;

INSERT INTO inbox_message (consumer_name, event_id, processed_at)
VALUES (:consumer, :event_id, CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING
RETURNING event_id;

-- Nếu RETURNING có dòng, áp dụng thay đổi nghiệp vụ.
-- Nếu không có dòng, event đã được xử lý; bỏ qua thay đổi lặp.

COMMIT;
```

Consumer chỉ ack message sau khi transaction database commit. Nếu consumer crash trước commit, inbox record và thay đổi nghiệp vụ cùng rollback, message có thể được giao lại. Nếu crash sau commit nhưng trước ack, message được giao lại nhưng unique key trong inbox khiến consumer bỏ qua tác dụng phụ lần hai.

Idempotency phải bao phủ toàn bộ tác dụng phụ mà consumer thực hiện. Nếu consumer cập nhật database rồi gọi một API khác, ghi inbox cùng database vẫn chưa bảo vệ API đó; consumer có thể cần một outbox riêng hoặc idempotency key phía API đích.

## 8. Idempotency key khi gọi API bên ngoài

Khi một API có thể thực hiện tác dụng phụ như thu tiền, tạo shipment hoặc gửi yêu cầu hoàn tiền, client nên gửi một idempotency key ổn định cho cùng một ý định nghiệp vụ.

Ví dụ:

```http
POST /payments
Idempotency-Key: payment-for-order-123
Content-Type: application/json

{
  "orderId": "123",
  "amount": "500000",
  "currency": "VND"
}
```

Nếu request timeout và ứng dụng gửi lại cùng key với cùng payload, dịch vụ ngoài có thể trả lại kết quả của lần xử lý đầu thay vì thu tiền lần hai. Key cần được tạo từ định danh nghiệp vụ ổn định, không tạo UUID mới cho mỗi lần retry.

Một API idempotent tốt thường:

- Lưu key cùng kết quả hoặc trạng thái của request.
- Đảm bảo chỉ một thao tác nghiệp vụ được thực hiện cho một key.
- Trả lại kết quả cũ khi nhận lại cùng key và payload tương ứng.
- Từ chối nếu cùng key được dùng với payload khác.
- Có thời hạn lưu key đủ dài so với cửa sổ retry và đối soát của client.
- Cung cấp API tra cứu trạng thái nếu request có thể ở trạng thái xử lý chưa rõ.

Idempotency key không tự đảm bảo thứ tự giữa hai request khác key. Nếu hai lệnh thay đổi cùng một đối tượng theo thứ tự bắt buộc, cần version, sequence, conditional update hoặc cơ chế điều phối riêng.

## 9. Callback sau COMMIT không giống transactional outbox

Nhiều framework có hook như `afterCommit`, transaction synchronization hoặc callback chạy sau khi transaction commit. Hook này hữu ích để tránh gọi dịch vụ ngoài trước commit, nhưng nếu callback chỉ tồn tại trong bộ nhớ process, nó không bền vững qua crash.

```text
BEGIN
  ghi order
  đăng ký afterCommit callback trong memory
COMMIT
  process crash trước callback

Kết quả: order đã commit, callback bị mất.
```

Transactional outbox ghi một dòng event vào database trong transaction. Worker có thể tìm lại dòng đó sau restart. Vì vậy:

| Cơ chế | Chạy lúc nào? | Có bền vững qua process crash sau commit? |
|---|---|---|
| Gọi API trước commit | Trong transaction | Không bảo vệ tác dụng phụ khỏi rollback |
| Callback `afterCommit` trong memory | Sau commit | Không, nếu process chết trước callback |
| Transactional outbox | Event được ghi trước commit; worker gửi sau commit | Có, vì event nằm trong database đã commit |
| Job queue độc lập được enqueue sau commit | Sau commit | Có khoảng trống nếu process chết trước khi enqueue |

Nếu một job queue dùng chính database và enqueue record nằm trong cùng transaction với dữ liệu nghiệp vụ, về bản chất nó có thể là một dạng outbox. Nếu queue nằm ở hệ thống khác, enqueue sau commit vẫn có dual-write gap trừ khi có giao thức tích hợp đáng tin cậy.

## 10. Saga và compensating action

Transactional outbox bảo đảm thông báo được lưu cùng transaction local. Nhưng nếu một nghiệp vụ kéo dài qua nhiều dịch vụ độc lập, mỗi dịch vụ có transaction riêng, không thể rollback tất cả bằng một lệnh SQL.

**Saga** chia quy trình thành các bước local transaction. Mỗi bước có thể có một hành động bù trừ (compensating action) để đưa nghiệp vụ về trạng thái chấp nhận được khi bước sau thất bại.

Ví dụ đặt hàng:

| Bước | Local action | Hành động bù trừ có thể dùng |
|---|---|---|
| 1 | Giữ tồn kho | Hủy reservation, trả tồn kho |
| 2 | Thu tiền hoặc authorize payment | Void authorization hoặc refund nếu đã capture |
| 3 | Tạo shipment | Hủy shipment nếu hãng vận chuyển cho phép |
| 4 | Xác nhận đơn hàng | Chuyển trạng thái sang `CANCELLED` hoặc `COMPENSATION_REQUIRED` |

Một saga có thể chạy theo orchestration (một coordinator quản lý bước) hoặc choreography (các dịch vụ phản ứng với event). Mỗi bước cần trạng thái bền vững, timeout, retry, idempotency và khả năng tiếp tục sau restart.

Compensation không phải rollback vật lý hoàn hảo. Nếu email đã gửi, không thể làm người nhận quên email. Nếu khoản thanh toán đã capture, hành động bù trừ thường là tạo refund mới, có lịch sử và thời điểm riêng. Vì vậy, trạng thái cuối có thể là `COMPENSATED` hoặc `MANUAL_REVIEW`, chứ không nhất thiết giống như chưa từng xảy ra.

## 11. Khi nào dùng two-phase commit?

Two-phase commit (2PC) là giao thức phối hợp transaction giữa nhiều resource manager có hỗ trợ XA hoặc distributed transaction. Coordinator yêu cầu các participant prepare trước; nếu tất cả sẵn sàng, coordinator ra quyết định commit, nếu không thì rollback.

```text
Coordinator       Database A       Database B
     |                 |                |
     |---- PREPARE --->|                |
     |---------------- PREPARE ------->|
     |<--- READY ------|                |
     |<---------------- READY ---------|
     |                                  |
     |---- COMMIT ---->|                |
     |---------------- COMMIT -------->|
```

2PC có thể bảo đảm atomic commit giữa các resource manager tham gia đúng giao thức. Tuy nhiên:

- Dịch vụ HTTP, email provider hoặc API thanh toán thông thường không phải XA participant.
- Participant có thể giữ prepared transaction và khóa trong lúc chờ quyết định coordinator.
- Coordinator hoặc network failure có thể khiến participant ở trạng thái in-doubt.
- Vận hành, timeout, recovery log và cấu hình distributed transaction phức tạp.
- Chi phí round trip và thời gian giữ resource có thể làm giảm khả năng mở rộng.

Vì vậy, không nên mặc định dùng 2PC cho mọi lời gọi HTTP. Nó phù hợp khi các resource manager thực sự hỗ trợ distributed transaction và yêu cầu atomic commit đủ mạnh để chấp nhận chi phí vận hành. Với API ngoài không hỗ trợ 2PC, outbox, idempotency và saga thường phù hợp hơn.

## 12. Xử lý trạng thái COMMIT không rõ ràng

Một trường hợp khó là ứng dụng gửi `COMMIT` rồi mất kết nối trước khi nhận response. Không thể kết luận transaction đã rollback chỉ vì client nhận exception. Database có thể đã commit thành công nhưng phản hồi bị mất.

Nếu ứng dụng gọi dịch vụ ngoài ngay sau đó, nó có thể thực hiện tác dụng phụ cho một transaction thực ra chưa commit hoặc bỏ qua tác dụng phụ cho transaction đã commit.

Cách xử lý:

1. Gắn một request ID hoặc idempotency key ổn định vào bản ghi nghiệp vụ.
2. Khi kết quả commit không rõ, mở connection/transaction mới và tra cứu trạng thái bằng key đó.
3. Nếu transaction đã commit, tiếp tục từ trạng thái đã lưu hoặc để outbox worker xử lý.
4. Nếu không có bản ghi đã commit, xử lý lại theo quy tắc nghiệp vụ và cùng key.
5. Nếu trạng thái chưa thể xác định do database đang phục hồi hoặc chưa truy cập được, giữ trạng thái pending và retry tra cứu; không tạo một yêu cầu nghiệp vụ mới với key khác.

Outbox giúp đơn giản hóa việc này: ứng dụng không cần đoán callback có chạy sau commit hay không. Nếu commit thành công, outbox event tồn tại; nếu rollback, event không tồn tại. Worker dựa vào trạng thái bền vững đó để tiếp tục.

## 13. Thiết kế retry và backoff

Lỗi gọi dịch vụ ngoài thường được chia thành:

| Loại lỗi | Hành động thường phù hợp |
|---|---|
| Timeout hoặc mất kết nối | Kết quả có thể chưa rõ; retry với cùng idempotency key hoặc tra cứu trạng thái |
| HTTP 429 / rate limit | Tôn trọng `Retry-After` nếu có, áp dụng backoff |
| HTTP 5xx tạm thời | Retry có giới hạn với cùng request identity |
| HTTP 4xx do dữ liệu sai | Thường không retry tự động; chuyển trạng thái lỗi nghiệp vụ |
| Xác thực/ủy quyền thất bại | Sửa cấu hình hoặc credential; tránh retry liên tục |
| Serialization/deadlock trong consumer database | Retry toàn bộ local transaction theo chính sách |
| Kết quả nghiệp vụ từ chối | Ghi nhận kết quả và chuyển saga/state machine theo nhánh phù hợp |

Exponential backoff có jitter giúp giảm việc nhiều worker retry cùng lúc:

```text
delay = min(max_delay, base_delay * 2^attempt) + random_jitter
```

Phải có giới hạn số lần thử hoặc thời gian retry, sau đó chuyển sang dead-letter queue, trạng thái cần can thiệp hoặc quy trình đối soát. Không retry vô hạn một lỗi dữ liệu vĩnh viễn.

Mỗi lần retry phải giữ nguyên idempotency key và event ID. Tạo key mới cho mỗi lần thử sẽ làm mất khả năng nhận diện đó là cùng một ý định nghiệp vụ.

## 14. Giữ thứ tự event và tránh event cũ ghi đè event mới

Outbox có thể chứa nhiều event cho cùng một aggregate, ví dụ `OrderCreated`, `PaymentAuthorized`, `OrderCancelled`. Nếu worker gửi chúng không đúng thứ tự, consumer có thể nhận `OrderCancelled` trước `PaymentAuthorized`.

Khi thứ tự quan trọng:

- Gán sequence tăng đơn điệu theo từng aggregate.
- Gửi cùng aggregate vào cùng partition/key của broker nếu broker hỗ trợ ordering theo partition.
- Consumer kiểm tra sequence/version và từ chối hoặc trì hoãn event cũ đến muộn.
- Không xử lý đồng thời các event cùng aggregate nếu nghiệp vụ yêu cầu tuần tự.
- Thiết kế state transition có điều kiện, ví dụ chỉ cho phép `PENDING -> AUTHORIZED` khi version hiện tại phù hợp.

Ví dụ cập nhật trạng thái có version:

```sql
UPDATE order_projection
SET status = :new_status,
    last_event_seq = :event_seq
WHERE order_id = :order_id
  AND last_event_seq = :event_seq - 1;
```

Nếu không có dòng nào được cập nhật, event có thể bị trùng, đến sai thứ tự hoặc projection đang thiếu một event trước đó. Consumer cần phân loại và xử lý từng trường hợp thay vì bỏ qua mọi lỗi như nhau.

## 15. Các mẫu thiết kế theo nhu cầu

| Nhu cầu | Cách tiếp cận phù hợp |
|---|---|
| Chỉ cập nhật nhiều bảng trong cùng database | Một transaction database |
| Gửi event sau khi dữ liệu đã commit, cần không mất thông báo | Transactional outbox |
| Consumer có thể nhận event nhiều lần | Inbox table/unique event ID và xử lý idempotent |
| Gọi API thanh toán có thể timeout và retry | Idempotency key, tra cứu trạng thái và đối soát |
| Quy trình qua nhiều dịch vụ với các local transaction | Saga với state machine và compensating actions |
| Nhiều database/resource manager hỗ trợ XA và cần atomic commit | Cân nhắc 2PC với kế hoạch vận hành/recovery |
| Chỉ cần chạy callback sau commit trong ứng dụng đơn giản | `afterCommit` có thể hữu ích, nhưng không thay outbox nếu cần phục hồi sau crash |

Không có một mẫu duy nhất giải quyết mọi vấn đề. Hãy chọn theo yêu cầu mất dữ liệu, chấp nhận duplicate, thời gian hoàn tất, khả năng bù trừ và mức độ phối hợp mà các hệ thống tham gia hỗ trợ.

## 16. Những sai lầm thường gặp

**Gọi API trước commit vì muốn “mọi thứ nằm trong một transaction”.** API ngoài không tự tham gia transaction database. Nó có thể thành công dù database rollback.

**Gọi API sau commit rồi cho rằng không còn rủi ro.** Process có thể chết trước lời gọi; API có thể lỗi hoặc response có thể mất sau khi tác dụng phụ đã xảy ra.

**Dùng `afterCommit` thay cho outbox trong nghiệp vụ quan trọng.** Callback trong bộ nhớ không bền vững qua crash sau commit.

**Ghi outbox sau commit trong một transaction khác.** Vẫn tồn tại khoảng trống giữa commit nghiệp vụ và ghi event. Outbox phải được ghi trong cùng transaction với dữ liệu nghiệp vụ.

**Cho rằng outbox đảm bảo exactly-once delivery.** Relay có thể publish thành công rồi crash trước khi đánh dấu sent; event có thể được gửi lại. Consumer cần idempotency.

**Tạo idempotency key mới mỗi lần retry.** Dịch vụ ngoài sẽ xem đó là các yêu cầu khác nhau và có thể lặp tác dụng phụ.

**Đánh dấu event đã gửi trước khi publish.** Nếu process chết sau khi đánh dấu nhưng trước khi broker nhận, event có thể bị mất. Cần chấp nhận at-least-once và xử lý duplicate.

**Ack queue trước khi local transaction commit.** Nếu consumer crash sau ack nhưng trước commit, message có thể mất trong khi tác dụng phụ chưa được lưu.

**Giữ database transaction mở khi chờ HTTP.** Điều này kéo dài thời gian giữ khóa và kết nối, làm tăng contention và nguy cơ timeout.

**Dùng compensation như thể đó là rollback.** Hoàn tiền, hủy shipment hoặc gửi thông báo đính chính là hành động mới, có thể thất bại và cần được theo dõi như một bước saga.

## 17. Cách kiểm tra một luồng tích hợp

Khi xem xét code tạo dữ liệu rồi gọi dịch vụ ngoài, hãy lần theo các câu hỏi:

1. Transaction database bắt đầu và kết thúc ở đâu?
2. Những thay đổi nào phải commit cùng nhau trong database?
3. Lời gọi dịch vụ ngoài đang chạy trước hay sau commit?
4. Nếu process chết ngay sau commit, công việc gửi thông báo có còn được lưu bền vững không?
5. Nếu API thành công nhưng response mất, retry có tạo tác dụng phụ trùng không?
6. Idempotency key có ổn định qua mọi lần retry và được dịch vụ đích hỗ trợ không?
7. Outbox record có được ghi trong cùng transaction với dữ liệu nghiệp vụ không?
8. Relay có xử lý nhiều worker, claim lease, retry và dead-letter không?
9. Consumer có inbox/unique event ID và commit tác dụng phụ cùng inbox record không?
10. Event có cần giữ thứ tự theo aggregate hoặc version không?
11. Quy trình nhiều dịch vụ có state machine và compensation rõ ràng không?
12. Kết quả COMMIT không rõ được tra cứu bằng request ID/idempotency key như thế nào?
13. Có dashboard cho pending age, retry count, dead-letter, duplicate và compensation failure không?

Một bài kiểm thử lỗi hữu ích là chủ động dừng process tại các điểm: sau external success nhưng trước database commit; ngay sau database commit nhưng trước publish; sau publish nhưng trước đánh dấu sent; sau consumer commit nhưng trước ack. Mỗi điểm phải có kết quả phục hồi xác định và không tạo tác dụng phụ nghiệp vụ ngoài dự kiến.

## 18. Kết luận

Gọi dịch vụ ngoài trước `COMMIT` có thể tạo tác dụng phụ mà database không thể rollback, đồng thời giữ khóa trong lúc chờ mạng. Gọi sau `COMMIT` tránh việc dịch vụ ngoài chạy trước khi dữ liệu local được xác nhận, nhưng vẫn có khoảng trống nếu process chết hoặc API lỗi trước khi nhận thông báo.

Với tích hợp cần độ tin cậy, hãy ghi dữ liệu nghiệp vụ và outbox event trong cùng transaction; worker gửi event sau commit; consumer dùng inbox hoặc idempotency key để xử lý duplicate; API ngoài nhận cùng một idempotency key qua mọi lần retry. Khi quy trình đi qua nhiều dịch vụ có trạng thái riêng, dùng saga và compensating action. 2PC chỉ phù hợp khi các participant hỗ trợ distributed transaction và hệ thống chấp nhận chi phí vận hành của nó.

Mục tiêu thực tế không phải giả định rằng mạng không lỗi hoặc thông điệp chỉ đến đúng một lần. Mục tiêu là lưu được ý định cần thực hiện, có thể gửi lại sau sự cố, nhận diện request lặp và đưa toàn bộ quy trình về một trạng thái nghiệp vụ có thể giải thích và đối soát.
