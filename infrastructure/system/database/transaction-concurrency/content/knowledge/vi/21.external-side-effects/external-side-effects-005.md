# Inbox và nhận diện sự kiện đã xử lý ở phía tiêu thụ

Trong hệ thống hướng sự kiện, một message có thể được gửi lại nhiều lần. Broker có thể giao lại message khi consumer mất kết nối trước khi xác nhận, consumer có thể crash sau khi commit database nhưng trước khi ack, hoặc producer có thể gửi lại cùng một event sau timeout. Vì vậy, consumer không nên giả định mỗi message chỉ đến đúng một lần.

**Inbox pattern** là cách consumer lưu dấu sự kiện đã nhận và phối hợp dấu nhận đó với thay đổi nghiệp vụ trong cùng transaction database. Một khóa duy nhất trên định danh sự kiện giúp nhận ra message trùng. Nếu sự kiện đã được xử lý, consumer bỏ qua phần thay đổi nghiệp vụ lần nữa; nếu chưa, consumer ghi nhận sự kiện, thực hiện thay đổi và commit tất cả cùng nhau.

Mẫu này thường được dùng để xây dựng *idempotent consumer* (consumer có thể nhận lại cùng một message mà không lặp tác dụng nghiệp vụ). Nó phù hợp với hệ thống giao message theo kiểu *at-least-once*, nơi redelivery là hành vi bình thường.

Nguyên tắc cốt lõi:

> Ghi nhận sự kiện đã xử lý và thay đổi dữ liệu nghiệp vụ phải nằm trong cùng transaction. Chỉ ack message sau khi transaction đó commit thành công.

Nếu consumer đánh dấu message đã xử lý trước khi thay đổi nghiệp vụ hoàn tất, một lỗi giữa chừng có thể khiến message bị bỏ qua vĩnh viễn. Nếu consumer thay đổi dữ liệu trước rồi mới ghi dấu nhận trong transaction khác, một lần redelivery có thể áp dụng tác dụng nghiệp vụ lần thứ hai.

## 1. Vì sao consumer phải chịu được message trùng?

Nhiều message broker ưu tiên giao message ít nhất một lần thay vì bảo đảm mỗi message chỉ được giao đúng một lần trong mọi tình huống. Khi broker không nhận được xác nhận, nó không thể luôn biết consumer đã xử lý xong hay chưa, nên có thể giao lại.

Một lịch thường gặp:

```text
1. Broker giao event E cho consumer.
2. Consumer cập nhật database và COMMIT.
3. Consumer crash trước khi gửi ACK.
4. Broker không thấy ACK và giao lại event E.
5. Consumer chạy lại logic nghiệp vụ.
```

Ở bước 4, database đã lưu tác dụng của event E. Nếu consumer không nhận diện event đã xử lý, nó có thể trừ tồn kho lần thứ hai, tạo thêm ledger entry hoặc phát thêm một yêu cầu thanh toán.

Một tình huống khác cũng nguy hiểm:

```text
1. Consumer ghi dấu E là đã xử lý.
2. Consumer crash trước khi cập nhật đơn hàng.
3. Broker giao lại E.
4. Consumer thấy dấu đã xử lý và bỏ qua.
```

Lần này tác dụng nghiệp vụ chưa từng được commit nhưng message lại bị bỏ qua. Vì thế, dấu nhận và thay đổi nghiệp vụ cần cùng một ranh giới transaction.

### Duplicate delivery không nhất thiết là lỗi broker

Redelivery có thể xảy ra sau timeout, rebalance, mất kết nối, consumer restart hoặc lỗi xử lý tạm thời. Consumer nên coi message trùng là trường hợp cần xử lý bình thường. Cố gắng cấu hình broker để “không bao giờ giao trùng” không thay thế được idempotency ở phía consumer.

## 2. Inbox pattern hoạt động như thế nào?

Inbox là một bảng trong database của consumer, lưu các event mà consumer đã xử lý. Một schema đơn giản:

```sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    payload_hash VARCHAR(128),
    PRIMARY KEY (consumer_name, event_id)
);
```

Khóa chính ghép `(consumer_name, event_id)` cho phép mỗi consumer ghi nhận một event tối đa một lần. Một event có thể được nhiều consumer độc lập xử lý; ví dụ `billing-projection` và `shipping-service` đều có thể cần nhận cùng event `OrderPaid`.

Luồng xử lý:

```text
Broker giao event E
       |
       v
BEGIN transaction database
       |
       v
Thử INSERT (consumer_name, event_id) vào inbox
       |
       +---- Đã tồn tại --------------------+
       |                                   |
       |                                   v
       |                           Không áp dụng lại
       |                                   |
       +---- Insert thành công             |
                    |                      |
                    v                      |
          Thực hiện thay đổi nghiệp vụ     |
                    |                      |
                    v                      |
                  COMMIT <-----------------+
                    |
                    v
               ACK message
```

Nếu transaction thất bại trước commit, cả hàng inbox mới và thay đổi nghiệp vụ đều rollback. Broker không nhận ACK nên có thể giao lại. Nếu transaction đã commit nhưng ACK bị mất, lần giao lại tiếp theo gặp khóa duy nhất trong inbox và được nhận diện là duplicate.

## 3. Định danh sự kiện phải ổn định

Inbox chỉ hoạt động khi consumer có thể xác định hai lần giao có phải cùng một event hay không. Producer nên tạo một `event_id` ổn định và giữ nguyên ID đó trong mọi lần gửi lại cùng một event.

Ví dụ một envelope sự kiện:

```json
{
  "eventId": "evt-01J8Q4M6W3X7",
  "eventType": "OrderPaid",
  "eventVersion": 1,
  "occurredAt": "2026-11-14T09:30:00Z",
  "aggregateType": "Order",
  "aggregateId": "order-5001",
  "aggregateVersion": 12,
  "correlationId": "req-8d42",
  "payload": {
    "orderId": "order-5001",
    "paymentId": "pay-720",
    "amount": "1250000",
    "currency": "VND"
  }
}
```

Các trường có vai trò khác nhau:

- `eventId`: định danh duy nhất của một sự kiện cụ thể, dùng cho deduplication.
- `eventType`: tên loại sự kiện, giúp chọn handler.
- `eventVersion`: phiên bản schema của envelope/payload.
- `aggregateId`: định danh đối tượng nghiệp vụ mà event nói đến.
- `aggregateVersion`: thứ tự phiên bản thay đổi của aggregate nếu producer cung cấp.
- `correlationId` hoặc trace ID: hỗ trợ theo dõi một quy trình qua nhiều service.
- `occurredAt`: thời điểm nghiệp vụ xảy ra; không nên dùng riêng timestamp này làm khóa deduplication.

Không dùng nội dung payload làm event ID một cách tùy tiện. Hai sự kiện hợp lệ có thể có payload giống nhau nhưng là hai hành động khác nhau. Ngược lại, cùng một event được gửi lại có thể được serialize khác thứ tự thuộc tính JSON nhưng vẫn là cùng một event. Định danh nên được producer tạo và lưu bền vững cùng event.

### Phạm vi duy nhất của event ID

Nếu producer bảo đảm event ID duy nhất toàn hệ thống, có thể dùng `event_id` làm khóa chính. Nếu ID chỉ duy nhất trong một producer, tenant hoặc event source, hãy đưa phạm vi đó vào khóa:

```sql
PRIMARY KEY (consumer_name, event_source, tenant_id, event_id)
```

Điều quan trọng là hai event khác nhau không vô tình dùng cùng khóa dedup. Nếu dùng khóa quá rộng, consumer có thể bỏ qua một event hợp lệ chỉ vì event khác có cùng ID trong namespace khác.

## 4. Ghi inbox và thay đổi nghiệp vụ trong cùng transaction

Ví dụ consumer nhận `OrderPaid` và cần đánh dấu đơn đã thanh toán, đồng thời ghi một ledger entry.

Một cách triển khai khái niệm:

```sql
BEGIN;

-- Thử ghi dấu event. Chỉ tiếp tục nếu event_id mới với consumer này.
INSERT INTO consumer_inbox (
    consumer_name, event_id, event_type,
    received_at, processed_at, payload_hash
)
VALUES (
    'billing-consumer', :eventId, 'OrderPaid',
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :payloadHash
);

-- Áp dụng tác dụng nghiệp vụ trong cùng transaction.
UPDATE orders
SET payment_status = 'PAID',
    paid_at = :occurredAt
WHERE id = :orderId
  AND payment_status = 'PENDING';

INSERT INTO payment_ledger (
    payment_id, order_id, amount, currency
)
VALUES (
    :paymentId, :orderId, :amount, :currency
);

COMMIT;
```

Đoạn SQL là khung minh họa; ứng dụng phải kiểm tra điều kiện và số hàng bị ảnh hưởng, xử lý trường hợp trạng thái không phù hợp, đồng thời bảo đảm các ràng buộc ledger. Nếu bất kỳ bước bắt buộc nào thất bại, rollback toàn bộ transaction.

Điểm quan trọng không nằm ở việc bảng có tên `consumer_inbox`, mà ở quan hệ nguyên tử:

```text
Inbox record được commit  <=>  Business effect được commit
```

Nếu event đã được xử lý, lần giao lại không tạo ledger entry hoặc thay đổi đơn hàng lần nữa.

### Cách xử lý insert duplicate

Một unique constraint hoặc primary key phải phân xử hai lần nhận cùng event, kể cả khi chúng đến đồng thời. Không nên chỉ `SELECT` kiểm tra trước:

```sql
SELECT 1
FROM consumer_inbox
WHERE consumer_name = :consumer
  AND event_id = :eventId;
```

Hai transaction có thể cùng thấy chưa tồn tại rồi cùng tiếp tục. Khóa duy nhất ở database mới là cơ chế quyết định khi có cạnh tranh.

Một cách triển khai theo PostgreSQL:

```sql
INSERT INTO consumer_inbox (
    consumer_name, event_id, event_type,
    received_at, processed_at, payload_hash
)
VALUES (
    :consumer, :eventId, :eventType,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :payloadHash
)
ON CONFLICT (consumer_name, event_id) DO NOTHING
RETURNING event_id;
```

- Có một hàng được trả về: transaction đã claim event mới và có thể áp dụng tác dụng nghiệp vụ.
- Không có hàng được trả về: event đã có inbox record; đây là duplicate đối với consumer này và không được áp dụng tác dụng nghiệp vụ lần nữa.

Đây là cú pháp PostgreSQL. MySQL, SQL Server, Oracle và các hệ quản trị khác có cú pháp hoặc cách xử lý duplicate khác nhau. Với PostgreSQL, nếu dùng `INSERT` thường và để unique violation thoát ra, transaction sẽ ở trạng thái lỗi cho đến khi rollback hoặc rollback về savepoint; không thể đơn giản bắt exception rồi tiếp tục dùng transaction như bình thường. Hãy dùng câu lệnh conflict-handling phù hợp hoặc xử lý transaction riêng.

## 5. Vì sao ACK phải xảy ra sau COMMIT?

Consumer thường có hai hệ thống độc lập: broker và database ứng dụng. Nếu không dùng distributed transaction được hỗ trợ đầy đủ, không thể commit hai hệ thống như một thao tác nguyên tử duy nhất.

Thứ tự an toàn thông dụng là:

```text
1. Nhận message.
2. BEGIN database transaction.
3. Ghi inbox record nếu event chưa được xử lý.
4. Thực hiện thay đổi nghiệp vụ.
5. COMMIT database transaction.
6. ACK message cho broker.
```

Hai cửa sổ lỗi quan trọng:

| Sự cố xảy ra tại thời điểm | Hệ quả | Inbox xử lý ra sao? |
|---|---|---|
| Trước commit database | Transaction rollback hoặc chưa hoàn tất; broker chưa được ACK. | Message được giao lại; lần sau có thể xử lý từ đầu. |
| Sau commit, trước ACK | Business effect và inbox đã commit; broker có thể giao lại. | Duplicate bị nhận diện, bỏ qua tác dụng nghiệp vụ rồi ACK. |
| Sau ACK | Broker coi message đã được nhận; database đã commit trước đó. | Không cần xử lý lại. |

Nếu ACK trước commit, consumer có thể crash sau ACK nhưng trước commit. Broker không giao lại, trong khi database chưa có tác dụng nghiệp vụ: message bị mất ở góc nhìn của ứng dụng.

Nếu commit trước ACK, có thể có redelivery nhưng inbox xử lý được. Đây là lựa chọn ưu tiên vì duplicate có thể được nhận diện, còn mất message trước khi lưu tác dụng nghiệp vụ thường khó phục hồi hơn.

### ACK một message duplicate

Nếu inbox cho biết event đã được xử lý và transaction hiện tại không cần thay đổi nghiệp vụ, consumer vẫn cần ACK lần giao hiện tại. Nếu không ACK, broker có thể tiếp tục giao cùng message và consumer lặp lại thao tác dedup vô ích.

Nếu message duplicate có payload khác với payload đã lưu cho cùng event ID, đừng tự động ACK như duplicate bình thường mà không quan sát. Đây có thể là lỗi producer tái sử dụng ID hoặc vấn đề toàn vẹn dữ liệu. Hãy ghi nhận, cảnh báo và áp dụng chính sách quarantine/dead-letter phù hợp.

## 6. Xử lý hai lần giao cùng event đồng thời

Hai consumer instance có thể cùng nhận cùng một event do redelivery, rebalance hoặc cấu hình broker. Cả hai có thể bắt đầu transaction gần như cùng lúc.

```text
Consumer A: BEGIN
Consumer A: INSERT inbox (consumer-X, event-99) -> thành công

Consumer B: BEGIN
Consumer B: INSERT inbox (consumer-X, event-99) -> chờ unique key

Consumer A: cập nhật business data
Consumer A: COMMIT

Consumer B: tiếp tục, conflict/DO NOTHING -> duplicate
Consumer B: không áp dụng business effect
Consumer B: kết thúc transaction và ACK
```

Nếu A rollback thay vì commit, insert inbox của A cũng rollback. Khi đó B có thể insert thành công và trở thành consumer xử lý event. Unique constraint phối hợp các transaction đồng thời để chỉ một transaction claim được event tại một thời điểm.

Không cần khóa toàn bộ bảng inbox. Khóa duy nhất trên đúng phạm vi event là điểm phối hợp. Tuy nhiên, cần kiểm tra transaction timeout và xử lý deadlock/lock timeout nếu việc ghi inbox cùng các bảng nghiệp vụ tạo thứ tự khóa phức tạp.

### Tránh tách claim và xử lý thành hai transaction không cần thiết

Nếu transaction A insert một record `RECEIVED` rồi commit, sau đó transaction B hoặc worker khác mới cập nhật nghiệp vụ, hệ thống cần một state machine cho inbox, lease, timeout và recovery. Đó là một thiết kế xử lý dài hạn khác với mẫu transaction ngắn ở trên. Nếu không cần công việc dài, giữ inbox insert và business update trong cùng transaction sẽ đơn giản hơn và tránh trạng thái “đã nhận nhưng chưa xử lý” bị kẹt.

## 7. Inbox và idempotency không có nghĩa là exactly-once end-to-end

Inbox thường tạo ra kết quả nghiệp vụ **effectively-once** trong phạm vi một database và một consumer identity: cùng event ID chỉ làm thay đổi dữ liệu đã phối hợp transaction một lần.

Điều đó không có nghĩa message chỉ được broker giao đúng một lần. Message có thể được giao nhiều lần; consumer chỉ đảm bảo các lần giao lại không lặp tác dụng database đã bảo vệ.

Inbox cũng không tự bảo vệ tác dụng phụ ở hệ thống ngoài. Ví dụ:

```text
BEGIN database transaction
  insert inbox record
  update order status
  call payment provider
COMMIT
```

Nếu payment provider đã thu tiền nhưng database transaction rollback, inbox record cũng rollback. Khi message được giao lại, consumer có thể gọi payment provider lần nữa. Database không thể rollback một HTTP call đã thành công.

Đối với tác dụng phụ bên ngoài, cần một trong các cách phù hợp:

- Gửi idempotency key ổn định tới API bên ngoài nếu API hỗ trợ.
- Ghi một command vào outbox cùng transaction với inbox và business update; worker thực hiện lời gọi ngoài sau commit.
- Dùng saga và hành động bù trừ khi quy trình trải qua nhiều hệ thống.
- Lưu trạng thái từng bước để phục hồi khi kết quả từ hệ thống ngoài không xác định.

Không nên tuyên bố exactly-once chỉ vì có bảng inbox. Hãy mô tả chính xác phạm vi: giao message có thể lặp, database effect được deduplicate theo event ID, còn tác dụng phụ ngoài cần cơ chế idempotency hoặc phối hợp riêng.

## 8. Kết hợp inbox với transactional outbox

Inbox xử lý đầu vào của consumer; outbox giúp service phát sự kiện đầu ra một cách bền vững. Một consumer có thể nhận event, cập nhật database và phát một event mới. Khi đó có thể dùng cả hai:

```text
Broker nguồn
    |
    v
Consumer
    |
    v
BEGIN database transaction
  INSERT inbox record
  UPDATE business tables
  INSERT outbox event mới
COMMIT
    |
    v
ACK message nguồn
    |
    v
Outbox publisher gửi event mới tới broker đích
```

Ví dụ consumer nhận `OrderPaid`, cập nhật projection đơn hàng và tạo `InvoiceRequested`:

```sql
BEGIN;

-- Claim event nguồn theo consumer identity.
INSERT INTO consumer_inbox (
    consumer_name, event_id, event_type,
    received_at, processed_at
)
VALUES (
    'invoice-trigger', :sourceEventId, 'OrderPaid',
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
);

-- Tác dụng nghiệp vụ trong database của consumer.
UPDATE orders
SET payment_status = 'PAID'
WHERE id = :orderId
  AND payment_status = 'PENDING';

-- Ghi sự kiện đầu ra trong cùng transaction.
INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload, created_at
)
VALUES (
    :newEventId, :orderId, 'InvoiceRequested', :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
```

Trong thực tế phải kiểm tra row count và xử lý trường hợp trạng thái đã thay đổi theo quy tắc nghiệp vụ. Ví dụ SQL trên chỉ minh họa sự phối hợp transaction. Outbox publisher có thể gửi `InvoiceRequested` nhiều lần nếu crash sau khi gửi nhưng trước khi đánh dấu đã gửi; consumer tiếp theo cũng cần inbox hoặc idempotency tương ứng.

Inbox và outbox giải quyết hai hướng khác nhau:

| Pattern | Mục tiêu | Ghi nhận ở đâu? |
|---|---|---|
| Inbox | Nhận diện event đầu vào đã xử lý | Database của consumer |
| Outbox | Bảo đảm ý định phát event đầu ra được lưu cùng thay đổi nghiệp vụ | Database của producer |

## 9. Thứ tự sự kiện và event đến muộn

Deduplication chỉ trả lời câu hỏi “event ID này đã được xử lý chưa?”. Nó không bảo đảm các event đến đúng thứ tự.

Ví dụ một đơn hàng có hai event:

```text
OrderPaid       aggregateVersion = 12
OrderCancelled  aggregateVersion = 13
```

Nếu broker hoặc nhiều partition khiến consumer nhận `OrderCancelled` trước rồi mới nhận `OrderPaid`, inbox sẽ xem cả hai là event mới vì ID khác nhau. Consumer có thể vô tình áp dụng `OrderPaid` muộn và làm trạng thái đơn quay về `PAID`.

Các cách xử lý:

- Partition message theo `aggregateId` để giữ thứ tự trong phạm vi một aggregate nếu broker hỗ trợ.
- Mang `aggregateVersion` hoặc sequence number trong event và kiểm tra thứ tự ở consumer.
- Dùng conditional update để chỉ chấp nhận phiên bản mới hơn hoặc chuyển trạng thái hợp lệ.
- Lưu event đến muộn vào hàng chờ/reconciliation nếu cần chờ event trước.
- Thiết kế handler sao cho một số event có thể áp dụng độc lập hoặc giao hoán nếu nghiệp vụ cho phép.

Ví dụ projection có cột `last_event_version`:

```sql
UPDATE order_projection
SET status = :newStatus,
    last_event_version = :eventVersion
WHERE order_id = :orderId
  AND last_event_version = :eventVersion - 1;
```

Nếu update bằng `0` hàng, event có thể đến quá sớm, quá muộn, trùng về mặt phiên bản hoặc aggregate chưa tồn tại. Ứng dụng cần phân loại và xử lý thay vì coi mọi trường hợp là duplicate.

Không phải mọi event source đều cung cấp version liên tục. Nếu chỉ có timestamp, không nên dùng timestamp làm thứ tự tuyệt đối khi nhiều producer hoặc clock có thể lệch. Cần một sequence do nguồn nghiệp vụ phát hành hoặc quy tắc ordering rõ ràng.

## 10. Event ID trùng nhưng payload khác

Một event ID được xem là định danh bất biến. Nếu consumer đã lưu `event_id = E1` với payload hash `H1`, sau đó nhận lại `E1` nhưng payload hash là `H2`, có hai khả năng:

- Producer đã tái sử dụng event ID cho một nội dung khác.
- Một tầng trung gian hoặc serialization pipeline đã thay đổi payload ngoài hợp đồng.

Đây không phải duplicate bình thường. Nếu consumer chỉ kiểm tra khóa và bỏ qua, lỗi dữ liệu có thể bị che giấu.

Có thể lưu `payload_hash`, `event_type`, `event_source` và schema version trong inbox. Khi event ID đã tồn tại:

1. So sánh hash và metadata với record cũ.
2. Nếu khớp, xử lý như duplicate bình thường.
3. Nếu khác, ghi metric/log cảnh báo và đưa event vào quy trình điều tra hoặc dead-letter.
4. Không áp dụng payload mới dưới cùng event ID.

Hash cần được tính từ dạng canonical hoặc byte representation mà producer và consumer thống nhất. Hash JSON thô có thể khác chỉ vì thứ tự key hoặc khoảng trắng dù ý nghĩa payload không đổi. Nếu chỉ cần phát hiện ID bị tái sử dụng, một canonical serialization hoặc checksum do producer cung cấp có thể phù hợp hơn.

## 11. Trạng thái inbox cho xử lý dài hạn

Mẫu transaction ngắn thường chỉ cần một hàng inbox được insert và commit cùng business effect. Nhưng một số consumer phải xử lý công việc dài, chẳng hạn tải file lớn, gọi dịch vụ bên ngoài hoặc chạy pipeline nhiều phút. Không nên giữ một transaction database mở suốt thời gian đó.

Khi cần xử lý dài hạn, inbox có thể có state machine riêng:

```text
RECEIVED -> PROCESSING -> PROCESSED
                 |
                 +----> RETRY_WAIT
                 |
                 +----> FAILED / DEAD_LETTER
```

Schema minh họa:

```sql
CREATE TABLE consumer_inbox_jobs (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    lease_owner VARCHAR(120),
    lease_until TIMESTAMP,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    processed_at TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
```

Worker claim job bằng cập nhật có điều kiện hoặc locking read, đặt `lease_owner` và `lease_until`, rồi commit trạng thái `PROCESSING`. Công việc dài diễn ra ngoài transaction. Khi hoàn tất, worker mở transaction mới để lưu kết quả và chuyển `PROCESSED`.

Thiết kế này cần xử lý thêm:

- Worker chết khi đang `PROCESSING`: lease hết hạn để worker khác có thể claim lại.
- Hai worker cùng claim: điều kiện trạng thái/lease và khóa duy nhất phải ngăn claim trùng.
- Worker cũ tiếp tục sau khi lease đã hết: cần fencing token hoặc version để ngăn worker cũ ghi đè kết quả của worker mới.
- Tác dụng phụ bên ngoài bị thực hiện trước khi worker crash: cần idempotency key ở hệ thống nhận.
- Retry quá nhiều: cần attempt limit, backoff, deadline và dead-letter policy.

Inbox có lease là một hàng đợi công việc bền vững ở phía consumer; nó phức tạp hơn dedup record trong transaction ngắn. Chỉ thêm `PROCESSING` nếu thực sự cần xử lý qua nhiều transaction hoặc có công việc dài.

## 12. Poison message và dead-letter queue

Một message có thể luôn thất bại vì payload sai schema, thiếu dữ liệu bắt buộc, vi phạm quy tắc không thể phục hồi hoặc lỗi handler. Nếu consumer rollback và yêu cầu broker giao lại vô hạn, cùng message có thể chiếm tài nguyên và chặn tiến độ của các message khác.

Đó là **poison message**. Một chính sách xử lý thường gồm:

1. Phân loại lỗi tạm thời và lỗi không thể retry.
2. Giới hạn số attempt hoặc số lần redelivery.
3. Backoff giữa các lần thử cho lỗi tạm thời.
4. Sau ngưỡng, chuyển message sang dead-letter queue (DLQ) hoặc trạng thái quarantine.
5. Ghi lý do, exception, event ID, schema version và correlation ID để điều tra.
6. Cho phép sửa dữ liệu/handler rồi replay có kiểm soát.

Inbox không có nghĩa mọi message đều phải được đánh dấu processed. Nếu payload không hợp lệ và chưa có tác dụng nghiệp vụ, có thể ghi nhận trạng thái lỗi riêng hoặc để broker/DLQ quản lý. Quyết định ack, nack, reject hoặc chuyển DLQ phụ thuộc broker và chính sách vận hành.

Khi replay một message từ DLQ, giữ nguyên event ID nếu đó là cùng một event. Nếu inbox đã ghi nhận event là `PROCESSED`, replay cùng ID sẽ bị bỏ qua. Nếu muốn xử lý lại có chủ đích, phải có quy trình replay được thiết kế rõ: ví dụ xóa/đánh dấu lại record theo kiểm soát, dùng consumer namespace mới để dựng lại projection, hoặc phát một event sửa chữa mới. Không đổi event ID tùy tiện chỉ để vượt qua dedup, vì có thể nhân đôi tác dụng ngoài ý muốn.

## 13. Thời gian lưu inbox record và replay

Inbox record là dữ liệu chống xử lý trùng. Xóa nó quá sớm có thể khiến một message cũ được replay và áp dụng lại tác dụng nghiệp vụ.

Thời gian lưu nên dựa trên:

- Thời gian broker có thể redeliver message.
- Thời gian lưu message trong DLQ.
- Cửa sổ replay vận hành hoặc backfill.
- Khả năng producer gửi lại event cũ.
- Hậu quả nếu một event cũ được áp dụng lại.
- Dung lượng bảng và chiến lược partition/archive.

Nếu message có thể được replay sau sáu tháng nhưng inbox chỉ giữ ba mươi ngày, dedup không còn bảo vệ được sau ngày thứ ba mươi. Với tác dụng tài chính hoặc không thể lặp, cần lưu idempotency record lâu hơn hoặc giữ một khóa nghiệp vụ bền vững ở bảng domain/ledger.

Có thể partition inbox theo thời gian và archive record cũ, nhưng phải bảo đảm truy vấn dedup vẫn kiểm tra được toàn bộ cửa sổ event có thể quay lại. Nếu chuyển record sang archive mà đường xử lý không tra cứu archive, đó không còn là bảo vệ đầy đủ.

### Replay projection khác replay side effect

Một consumer xây dựng read model có thể được dựng lại từ event log bằng một consumer identity mới hoặc một projection generation mới. Nhưng consumer gửi tiền, gửi email hoặc tạo shipment không nên replay toàn bộ lịch sử như thể mọi event đều mới.

Tách consumer identity theo mục đích và generation. Nếu cần rebuild projection, tạo namespace/generation mới và chỉ ghi vào projection mới. Nếu cần chạy lại side effect, dùng quy trình nghiệp vụ bù trừ hoặc command riêng có idempotency, không xóa dấu inbox một cách tùy tiện.

## 14. Inbox và consumer identity

Khóa dedup thường cần bao gồm consumer identity vì mỗi consumer có trách nhiệm nghiệp vụ riêng. Ví dụ:

```text
consumer = billing-projection, event = evt-100 -> đã xử lý
consumer = shipping-service, event = evt-100 -> chưa xử lý
```

Hai consumer không được dùng chung một dấu nhận nếu cả hai đều cần áp dụng tác dụng riêng. Ngược lại, nếu một service có nhiều instance cùng xử lý một subscription/consumer group, chúng nên chia sẻ cùng `consumer_name` để database dedup giữa các instance.

Nếu đổi logic consumer và muốn replay có chủ đích, cần quyết định có giữ cùng identity hay tăng generation. Ví dụ `billing-projection-v2` có thể dựng một projection mới, nhưng nếu consumer tạo side effect thì generation mới có thể làm side effect cũ chạy lại. Identity phải phản ánh ranh giới tác dụng nghiệp vụ, không chỉ tên class hoặc tên pod.

## 15. Inbox trong Java và Spring

Một cách tổ chức phổ biến là để service xử lý database transaction và listener chỉ ACK sau khi service đã hoàn tất transaction.

Ví dụ khái niệm:

```java
@Service
public class OrderPaidHandler {
    private final InboxRepository inbox;
    private final OrderRepository orders;
    private final LedgerRepository ledger;

    @Transactional
    public HandleResult handle(OrderPaid event) {
        boolean claimed = inbox.insertIfAbsent(
            "billing-consumer",
            event.eventId(),
            event.eventType(),
            event.payloadHash()
        );

        if (!claimed) {
            return HandleResult.duplicate();
        }

        int changed = orders.markPaidIfPending(
            event.orderId(), event.occurredAt()
        );

        if (changed != 1) {
            throw new InvalidOrderTransitionException(event.orderId());
        }

        ledger.recordPayment(event);
        return HandleResult.processed();
    }
}
```

Listener ACK sau khi lời gọi service trả về:

```java
public void onMessage(Message message, Acknowledgment ack) {
    OrderPaid event = decoder.decode(message);

    handler.handle(event); // Proxy commit transaction trước khi trả về.

    ack.acknowledge();
}
```

Đây là ví dụ về thứ tự, không phải cấu hình broker hoàn chỉnh. Phải bảo đảm lời gọi `handler.handle` đi qua Spring transaction proxy; nếu self-invocation hoặc cấu hình transaction không đúng, commit có thể không xảy ra ở ranh giới mong đợi. Nếu listener container tự quản lý acknowledgment hoặc transaction, cần cấu hình nó để không ACK trước khi database transaction hoàn tất.

### Duplicate không phải lỗi xử lý

`HandleResult.duplicate()` là kết quả bình thường. Listener vẫn ACK message hiện tại sau khi xác nhận inbox record đã commit từ lần xử lý trước. Không nên ném exception chỉ vì duplicate, nếu không broker có thể liên tục redeliver một message vốn đã hoàn tất.

### Đảm bảo insertIfAbsent là nguyên tử

`inbox.insertIfAbsent` phải dựa vào unique constraint và câu lệnh conflict-handling nguyên tử. Không triển khai bằng `SELECT` rồi `INSERT` mà không có constraint. Nếu insert duplicate gây exception, cần xử lý transaction theo semantics database; ví dụ PostgreSQL cần `ON CONFLICT DO NOTHING` hoặc rollback transaction/savepoint trước khi tiếp tục.

## 16. Những lỗi thiết kế thường gặp

- **ACK trước commit:** consumer crash có thể làm broker không giao lại message dù business effect chưa được lưu.
- **Ghi inbox và business data ở hai transaction:** có thể tạo dấu đã xử lý nhưng chưa có tác dụng, hoặc tác dụng đã có nhưng chưa có dấu dedup.
- **Kiểm tra inbox bằng SELECT đơn thuần:** hai consumer đồng thời có thể cùng thấy event chưa tồn tại. Dùng unique constraint và insert-if-absent nguyên tử.
- **Dùng timestamp hoặc payload làm event ID:** có thể gộp nhầm hai event khác nhau hoặc không nhận diện được cùng event sau serialize khác.
- **Dùng một inbox identity cho nhiều consumer độc lập:** consumer thứ hai có thể bị bỏ qua dù chưa áp dụng tác dụng riêng.
- **Không kiểm tra payload khi event ID trùng:** producer tái sử dụng ID có thể bị che giấu.
- **Cho rằng inbox bảo vệ HTTP call bên ngoài:** transaction database không rollback được tác dụng ở dịch vụ khác. Dùng idempotency key, outbox hoặc saga.
- **Coi dedup là ordering:** event mới có thể đến trước event cũ; cần aggregate version hoặc cơ chế ordering.
- **Xóa inbox record quá sớm:** replay cũ có thể áp dụng lại tác dụng nghiệp vụ.
- **Replay bằng cách đổi event ID:** có thể làm cùng một ý định trở thành một event mới và lặp side effect.
- **Đánh dấu `PROCESSED` trước khi xử lý xong công việc dài:** crash có thể làm mất công việc. Với xử lý dài, dùng state machine, lease và fencing token.
- **Retry poison message vô hạn:** một message lỗi cố định có thể chiếm consumer. Dùng giới hạn retry và DLQ.

## 17. Cách thiết kế một consumer idempotent

Khi xây dựng consumer mới, hãy xác định:

1. Event ID do ai tạo và có ổn định qua mọi lần redelivery không?
2. Event ID duy nhất trong phạm vi nào: toàn hệ thống, producer, tenant hay aggregate?
3. Consumer identity nào đại diện cho tác dụng nghiệp vụ cần dedup?
4. Inbox record và các thay đổi database nào phải commit cùng nhau?
5. Câu lệnh insert-if-absent dựa trên unique constraint nào?
6. Consumer ACK ở thời điểm nào so với commit?
7. Nếu commit thành công nhưng ACK thất bại, lần redelivery sẽ được xử lý ra sao?
8. Nếu event ID giống nhưng payload khác, hệ thống cảnh báo và quarantine thế nào?
9. Event đến sai thứ tự được phát hiện bằng aggregate version hoặc sequence nào?
10. Tác dụng phụ ngoài database được bảo vệ bằng idempotency key, outbox hay saga nào?
11. Inbox record được lưu bao lâu so với cửa sổ redelivery và replay?
12. Poison message được retry, dead-letter và replay theo quy trình nào?
13. Nếu xử lý dài, lease, timeout, fencing token và recovery được quản lý ra sao?
14. Metric nào theo dõi duplicate rate, processing failures, redelivery và DLQ?

Một consumer đáng tin cậy phải có thể nhận lại cùng một event mà không nhân đôi tác dụng nghiệp vụ đã commit, đồng thời không đánh dấu hoàn tất khi tác dụng chưa được lưu. Inbox, unique constraint, transaction boundary và ACK ordering phối hợp để đạt mục tiêu đó.

## 18. Kết luận

Inbox pattern giúp consumer nhận diện sự kiện đã xử lý bằng một record bền vững, thường được khóa duy nhất theo consumer identity và event ID. Khi nhận một event mới, consumer ghi inbox record, thực hiện các thay đổi nghiệp vụ và commit trong cùng transaction. Sau commit mới ACK broker. Nếu ACK bị mất, event có thể được giao lại nhưng unique constraint giúp nhận diện duplicate và ngăn lặp tác dụng database.

Inbox không biến broker thành hệ thống giao đúng một lần end-to-end. Nó tạo khả năng xử lý lặp an toàn trong phạm vi dữ liệu được bảo vệ bởi cùng transaction. Tác dụng phụ bên ngoài cần idempotency hoặc outbox/saga riêng; event ordering cần sequence/version; message lỗi cần retry có giới hạn và DLQ; inbox record phải được lưu đủ lâu để bao phủ cửa sổ replay. Thiết kế đúng các ranh giới đó giúp consumer chịu được redelivery, crash và xử lý đồng thời mà vẫn giữ trạng thái nghiệp vụ nhất quán.
