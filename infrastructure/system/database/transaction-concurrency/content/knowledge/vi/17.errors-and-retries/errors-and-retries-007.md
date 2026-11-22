# Bảo đảm kết quả không bị lặp khi thao tác được thực thi lại

Trong hệ thống phân tán, một yêu cầu có thể được gửi nhiều lần dù người dùng chỉ bấm nút một lần. Client có thể timeout khi server đã xử lý xong nhưng phản hồi chưa đến nơi; worker có thể nhận lại một message sau khi mất kết nối; ứng dụng có thể retry transaction sau deadlock hoặc lỗi serialization. Nếu mỗi lần thực thi đều tạo ra một hiệu ứng mới, hệ thống có thể trừ tiền, tạo đơn hàng hoặc gửi thông báo nhiều lần.

**Idempotency (tính lặp an toàn)** là khả năng thực hiện cùng một yêu cầu nhiều lần mà kết quả nghiệp vụ cuối cùng tương đương với việc thực hiện một lần. Một cách phổ biến để đạt được điều đó là gắn yêu cầu với một **idempotency key**, lưu khóa này bằng ràng buộc `UNIQUE`, và ghi nhận kết quả xử lý trong cùng transaction với thay đổi nghiệp vụ.

## 1. Vì sao một thao tác có thể được thực thi lại?

Giả sử ứng dụng bán hàng gửi yêu cầu thanh toán 500.000 đồng. Server xử lý yêu cầu và commit giao dịch vào database, nhưng phản hồi bị mất trên đường truyền. Client chỉ nhìn thấy timeout.

Client không thể biết chắc điều gì đã xảy ra:

- Yêu cầu chưa đến server.
- Server nhận yêu cầu nhưng chưa xử lý.
- Server xử lý thất bại và rollback.
- Server đã commit thành công nhưng phản hồi bị mất.

Nếu client gửi lại một yêu cầu mới mà server không nhận diện đó là cùng thao tác, hệ thống có thể tạo hai khoản thanh toán.

```text
Client                         Server / Database
  │                                   │
  ├──── POST /payments ──────────────▶│
  │                                   ├── tạo thanh toán
  │                                   ├── COMMIT
  │                                   │
  │          phản hồi bị mất           │
  ◀──────────── timeout ──────────────┤
  │                                   │
  ├──── gửi lại yêu cầu ─────────────▶│
  │                                   ├── nếu không chống lặp:
  │                                   │   có thể tạo thanh toán thứ hai
```

Đây là lý do retry không thể chỉ được xem là “gửi lại cùng câu lệnh”. Ứng dụng cần một cách nhận diện cùng một ý định nghiệp vụ qua nhiều lần truyền hoặc thực thi.

## 2. Idempotency có nghĩa là gì?

Một thao tác idempotent có thể được áp dụng nhiều lần mà trạng thái cuối không thay đổi thêm sau lần đầu.

Ví dụ:

```sql
UPDATE users
SET enabled = TRUE
WHERE id = 101;
```

Chạy câu lệnh này một lần hay nhiều lần vẫn đưa `enabled` về `TRUE`. Đây là thao tác có tính lặp an toàn nếu không có side effect khác như tăng bộ đếm, phát sự kiện hoặc ghi lịch sử mỗi lần chạy.

Ngược lại:

```sql
UPDATE accounts
SET balance = balance - 100000
WHERE id = 101;
```

Mỗi lần chạy đều trừ thêm tiền. Đây không phải thao tác idempotent. Nếu client retry sau timeout mà server thực thi lại câu lệnh, số dư có thể bị trừ hai lần.

Có thể so sánh:

| Kiểu thao tác | Ví dụ | Thực hiện lặp |
|---|---|---|
| Gán trạng thái | `enabled = TRUE` | Trạng thái vẫn là TRUE |
| Xóa theo định danh | Xóa tài nguyên có id xác định | Tài nguyên vẫn ở trạng thái không tồn tại; phản hồi có thể khác |
| Cộng/trừ | `balance = balance + amount` | Mỗi lần tạo thêm thay đổi |
| Tạo bản ghi mới | `INSERT` một đơn hàng | Có thể tạo nhiều đơn nếu không có khóa chống lặp |
| Gửi email | Gửi cùng nội dung nhiều lần | Người nhận có thể nhận nhiều email |

Idempotency nói về **hiệu ứng nghiệp vụ**, không yêu cầu mọi lần gọi phải trả về cùng mã HTTP hoặc cùng thời gian phản hồi. Ví dụ, lần đầu có thể trả `201 Created`, lần gửi lại có thể trả kết quả đã lưu với mã `200 OK`; cả hai vẫn đại diện cho cùng một kết quả nghiệp vụ.

## 3. Idempotency key nhận diện cùng một yêu cầu

Client tạo một khóa duy nhất cho một ý định nghiệp vụ và gửi khóa đó cùng yêu cầu. Nếu cần retry, client phải gửi lại **chính khóa cũ**.

Ví dụ:

```http
POST /payments
Idempotency-Key: 9f2c1a1e-7b6a-4d7c-a3c0-4d8f8a2e7c11
Content-Type: application/json

{
  "orderId": "ORD-2026-00125",
  "amount": 500000,
  "currency": "VND"
}
```

Nếu client timeout, nó gửi lại cùng request và cùng `Idempotency-Key`. Server dùng khóa để nhận ra đây là lần thực thi lại của cùng thao tác.

Không nên tạo một idempotency key mới cho mỗi lần retry. Nếu mỗi lần gửi có key mới, server sẽ xem chúng là những yêu cầu độc lập và cơ chế chống lặp không còn tác dụng.

### Phạm vi của khóa

Một key cần có phạm vi xác định. Thực tế thường dùng tổ hợp:

```text
tenant_id + operation_name + idempotency_key
```

Ví dụ, key `abc-123` của tenant A khi tạo payment không nhất thiết phải xung đột với key `abc-123` của tenant B hoặc một thao tác khác. Phạm vi cần phù hợp với hợp đồng API và ranh giới nghiệp vụ.

Client nên tạo key đủ khó trùng, thường dùng UUID ngẫu nhiên hoặc một định danh ngẫu nhiên có độ dài phù hợp. Không nên dùng email, số điện thoại hay dữ liệu cá nhân làm key trực tiếp vì chúng có thể lộ thông tin và dễ bị tái sử dụng ngoài ý muốn.

## 4. Lưu idempotency key bằng UNIQUE constraint

Database cần bảo vệ tính duy nhất của key vì hai request có thể đến đồng thời. Một bảng minh họa:

```sql
CREATE TABLE idempotency_requests (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    operation_name VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(120) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL,
    response_code INTEGER,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    CONSTRAINT uq_idempotency_scope_key
        UNIQUE (tenant_id, operation_name, idempotency_key)
);
```

Các trường chính:

- `tenant_id`: chủ thể sở hữu yêu cầu, chẳng hạn khách hàng hoặc tổ chức.
- `operation_name`: loại thao tác được bảo vệ, ví dụ `CREATE_PAYMENT`.
- `idempotency_key`: định danh do client gửi.
- `request_hash`: dấu vân tay của nội dung nghiệp vụ đã chuẩn hóa.
- `status`: trạng thái xử lý, ví dụ `PROCESSING`, `SUCCEEDED` hoặc `FAILED_FINAL`.
- `response_code`, `response_body`: kết quả có thể phát lại cho lần retry.

Ràng buộc `UNIQUE` là thành phần quyết định để hai transaction không thể cùng sở hữu một key trong cùng phạm vi. Kiểm tra `SELECT` trước khi `INSERT` không thay thế được ràng buộc này vì hai giao dịch có thể cùng đọc kết quả rỗng.

## 5. Lưu kết quả và thay đổi nghiệp vụ trong cùng transaction

Với thao tác chỉ thay đổi dữ liệu trong cùng một database, thiết kế đơn giản và an toàn là ghi idempotency record, thực hiện thay đổi nghiệp vụ, rồi lưu kết quả trả về trong **một transaction nguyên tử**.

Luồng xử lý:

1. Bắt đầu transaction.
2. Thử chèn idempotency key với `UNIQUE` constraint.
3. Nếu chèn thành công, transaction hiện tại là chủ sở hữu lần xử lý này.
4. Thực hiện thay đổi nghiệp vụ.
5. Lưu trạng thái hoàn tất và kết quả phản hồi vào idempotency record.
6. Commit tất cả thay đổi cùng lúc.
7. Nếu key đã tồn tại, đọc record hiện có, so sánh request hash và phát lại kết quả đã lưu.

Ví dụ với PostgreSQL:

```sql
BEGIN;

INSERT INTO idempotency_requests (
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    status
)
VALUES (
    7,
    'CREATE_PAYMENT',
    '9f2c1a1e-7b6a-4d7c-a3c0-4d8f8a2e7c11',
    'sha256-of-canonical-request',
    'PROCESSING'
)
ON CONFLICT (tenant_id, operation_name, idempotency_key)
DO NOTHING
RETURNING id;

-- Nếu INSERT trả về id:
--   tạo payment và lưu kết quả vào cùng transaction.
-- Nếu không trả về hàng:
--   đọc idempotency record hiện có, kiểm tra request_hash,
--   rồi trả kết quả đã lưu.

COMMIT;
```

Đây là khung SQL minh họa; phần rẽ nhánh phụ thuộc vào ứng dụng và driver. Không được commit một idempotency record `PROCESSING` rồi mới xử lý payment nếu đang dùng mô hình transaction nguyên tử này. Trạng thái `PROCESSING` được chèn nhưng chưa commit nên transaction khác không nhìn thấy nó như một kết quả đã công bố.

### Vì sao phải lưu record cùng transaction?

Hãy xét hai cách ghi riêng rẽ:

**Ghi record trước, commit, rồi mới tạo payment:** nếu server chết sau khi commit record nhưng trước khi tạo payment, lần retry thấy key đã tồn tại nhưng không có payment. Hệ thống có thể trả một kết quả không đúng hoặc mắc kẹt ở trạng thái đang xử lý.

**Tạo payment trước, commit, rồi mới lưu idempotency record:** nếu server chết sau khi payment commit nhưng trước khi lưu key, lần retry không nhận ra thao tác đã thực hiện và có thể tạo payment thứ hai.

Nếu payment và idempotency record nằm trong cùng transaction, database commit cả hai hoặc rollback cả hai:

```text
BEGIN
  INSERT idempotency record
  INSERT payment / cập nhật dữ liệu nghiệp vụ
  UPDATE idempotency record với kết quả
COMMIT

Kết quả:
  tất cả cùng commit, hoặc tất cả cùng rollback
```

Nhờ vậy, nếu server mất kết nối sau commit, lần retry có thể tìm thấy record đã hoàn tất và trả lại kết quả cũ.

## 6. Hai request cùng key đến đồng thời

Giả sử `T1` và `T2` cùng gửi một key `K` với cùng nội dung request.

Với unique index, một transaction giành quyền chèn key trước. Transaction còn lại phải đợi kết quả của transaction đang sở hữu khóa duy nhất hoặc được DBMS xử lý theo cơ chế tương đương.

```text
T1                                      T2
-----------------------------------     -----------------------------------
BEGIN                                   BEGIN
INSERT idempotency key K                
                                        INSERT key K → chờ xung đột UNIQUE
Tạo payment                             đang chờ
Lưu response                            đang chờ
COMMIT                                  đang chờ
                                        INSERT không tạo hàng do conflict
                                        SELECT record K đã commit
                                        Trả response đã lưu
```

Nếu `T1` commit, `T2` nhận biết key đã tồn tại và phát lại kết quả. Nếu `T1` rollback, `T2` có thể giành quyền chèn key và thực hiện thao tác. Vì vậy, một lần thử lại không tự động thất bại chỉ vì request đầu tiên đã từng bắt đầu.

Trong PostgreSQL ở `READ COMMITTED`, `INSERT ... ON CONFLICT DO NOTHING` có thể bỏ qua insert do một transaction khác vừa commit một khóa xung đột mà snapshot của câu lệnh chưa nhìn thấy. Ở câu lệnh tiếp theo, một snapshot mới có thể đọc record đã commit. Với isolation level khác hoặc DBMS khác, ứng dụng có thể nhận serialization error hoặc phải retry transaction; cần dựa vào semantics cụ thể.

## 7. Cùng key nhưng nội dung request khác nhau

Một key đại diện cho một ý định nghiệp vụ. Vì vậy, nếu cùng key được gửi lại với amount hoặc order khác, server không nên âm thầm trả kết quả cũ hoặc thực hiện yêu cầu mới.

Ví dụ:

```text
Lần đầu:
  key = K
  orderId = ORD-1
  amount = 500000

Lần sau:
  key = K
  orderId = ORD-2
  amount = 900000
```

Hai request có cùng key nhưng khác nội dung. Server nên phát hiện sự không nhất quán và trả lỗi xung đột phù hợp, thường là HTTP `409 Conflict` theo hợp đồng API.

`request_hash` giúp so sánh nội dung. Hash nên được tạo từ biểu diễn chuẩn hóa của các trường có ý nghĩa nghiệp vụ, chẳng hạn:

```text
canonical_request = {
  tenantId,
  operationName,
  orderId,
  amount,
  currency
}

request_hash = SHA-256(canonical_request)
```

Không nên hash JSON thô nếu thứ tự thuộc tính, khoảng trắng, định dạng số hoặc cách biểu diễn Unicode có thể thay đổi mà không làm thay đổi ý nghĩa request. Hãy chuẩn hóa dữ liệu trước khi hash và chỉ đưa các trường quyết định nghiệp vụ vào fingerprint.

## 8. Phát lại kết quả cho lần retry

Nếu key đã tồn tại và request hash khớp, server có thể trả lại kết quả đã lưu. Tùy API, record có thể lưu:

- HTTP status code hoặc mã kết quả nghiệp vụ.
- Payment/order id đã tạo.
- Response body đã chuẩn hóa.
- Thời điểm hoàn tất.
- Các header cần thiết để tái tạo phản hồi, nếu hợp đồng API yêu cầu.

Ví dụ response ban đầu:

```json
{
  "paymentId": "PAY-90125",
  "status": "SUCCEEDED",
  "amount": 500000,
  "currency": "VND"
}
```

Khi client gửi lại cùng key và cùng nội dung, server trả lại `PAY-90125` thay vì tạo `PAY-90126`.

Không phải mọi header đều cần lưu. Không nên lưu dữ liệu bí mật như số thẻ thanh toán đầy đủ, access token hoặc thông tin xác thực trong response cache. Chỉ lưu dữ liệu cần thiết để tái tạo kết quả theo hợp đồng API và áp dụng chính sách bảo vệ dữ liệu phù hợp.

## 9. Trạng thái PROCESSING và xử lý request đang chạy

Có hai thiết kế thường gặp.

### Thiết kế nguyên tử trong một transaction

Record `PROCESSING`, thay đổi nghiệp vụ và kết quả hoàn tất nằm trong cùng transaction. Request trùng key sẽ chờ unique conflict được giải quyết. Sau khi transaction đầu commit, request sau đọc được kết quả hoàn tất; nếu transaction đầu rollback, request sau có thể thực hiện.

Ưu điểm là không để lại record `PROCESSING` đã commit mà không có tiến trình sở hữu. Thiết kế này phù hợp khi phần xử lý database ngắn và có thể hoàn tất trong một transaction.

### Thiết kế trạng thái bền vững nhiều bước

Với công việc dài hoặc cần gọi dịch vụ ngoài, ứng dụng có thể commit trạng thái `PROCESSING` trước, sau đó worker xử lý và chuyển sang `SUCCEEDED` hoặc `FAILED_FINAL`.

Thiết kế này cần thêm cơ chế điều phối:

- `owner_token` hoặc lease để xác định worker đang sở hữu công việc.
- `lease_expires_at` để nhận biết worker đã chết hoặc giữ việc quá lâu.
- Cơ chế claim/renew lease có tính nguyên tử.
- Quy trình phục hồi job quá hạn và tránh hai worker cùng thực hiện side effect.
- Trạng thái lỗi có thể retry và lỗi cuối cùng không nên retry.

Nếu request trùng key đến khi trạng thái đã commit là `PROCESSING`, API có thể trả `202 Accepted`, thông tin trạng thái để polling hoặc một lỗi “đang xử lý” theo hợp đồng. Không nên tự ý coi mọi `PROCESSING` là thất bại rồi bắt đầu thao tác lần nữa.

Hai thiết kế này giải quyết các nhu cầu khác nhau. Không nên trộn chúng mà thiếu quy tắc rõ ràng về transaction, quyền sở hữu và phục hồi.

## 10. Idempotency với side effect bên ngoài database

Transaction của database chỉ bảo đảm nguyên tử cho các thay đổi thuộc database đó. Nó không thể rollback một khoản tiền đã bị cổng thanh toán trừ, email đã gửi hoặc message đã được broker nhận.

Ví dụ:

```text
BEGIN DATABASE TRANSACTION
  tạo payment record
  gọi cổng thanh toán
COMMIT
```

Nếu cổng thanh toán thành công nhưng database transaction rollback, hai hệ thống không còn đồng bộ. Nếu server timeout rồi gọi cổng thanh toán lại, khách hàng có thể bị trừ tiền hai lần.

### Dùng idempotency key ở nhà cung cấp ngoài

Nếu cổng thanh toán hỗ trợ idempotency, hãy truyền một key ổn định cho cùng payment intent. Khi retry, gửi lại cùng key để nhà cung cấp nhận diện cùng thao tác. Key nội bộ và key bên ngoài nên có ánh xạ rõ ràng để có thể điều tra và đối soát.

Không nên giả định nhà cung cấp giữ key vô thời hạn hoặc áp dụng cùng phạm vi key. Cần xem tài liệu về thời gian lưu, cách xử lý payload khác nhau và trạng thái khi request timeout.

### Transactional outbox

Với sự kiện cần phát ra sau khi cập nhật database, có thể ghi sự kiện vào outbox cùng transaction:

```sql
BEGIN;

INSERT INTO orders (order_id, status)
VALUES ('ORD-125', 'CONFIRMED');

INSERT INTO outbox_events (event_id, event_type, payload)
VALUES ('EVT-9001', 'OrderConfirmed', '{...}');

COMMIT;
```

Worker đọc outbox và gửi sự kiện tới broker. Nếu worker gửi thành công nhưng chết trước khi đánh dấu sự kiện đã gửi, nó có thể gửi lại. Vì vậy, outbox bảo đảm sự kiện được lưu cùng transaction nghiệp vụ và có thể phát lại, nhưng consumer vẫn cần deduplicate hoặc xử lý idempotent.

## 11. Idempotent consumer và bảng inbox

Message broker thường cung cấp giao nhận ít nhất một lần (at-least-once) trong nhiều cấu hình. Consumer có thể nhận cùng event nhiều lần do retry, redelivery hoặc crash sau khi xử lý nhưng trước khi ACK.

Một cách chống lặp là lưu `event_id` đã xử lý trong bảng inbox với unique constraint:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_processed_event
        UNIQUE (consumer_name, event_id)
);
```

Consumer xử lý message trong cùng transaction:

```text
BEGIN

INSERT processed_events(consumer_name, event_id)
  -- nếu đã tồn tại thì không xử lý nghiệp vụ lần nữa

Nếu insert thành công:
  cập nhật dữ liệu nghiệp vụ

COMMIT
ACK message
```

Nếu insert inbox và thay đổi nghiệp vụ nằm trong cùng transaction, crash trước commit sẽ rollback cả hai; broker có thể gửi lại và consumer xử lý lại. Nếu transaction commit xong nhưng ACK bị mất, message có thể được gửi lại; unique event id khiến consumer nhận ra đã xử lý và bỏ qua phần nghiệp vụ.

Nếu cập nhật nghiệp vụ và ghi inbox ở hai transaction riêng, vẫn có khoảng trống dẫn đến xử lý lặp hoặc bỏ sót. Ranh giới transaction cần bao trùm cả dấu vết deduplication và hiệu ứng database mà nó bảo vệ.

## 12. Exactly-once và giới hạn thực tế

“Exactly-once” thường được dùng để mô tả mong muốn một nghiệp vụ chỉ tạo ra một hiệu ứng, dù message hoặc request có thể được gửi nhiều lần. Nhưng trên mạng, sender thường không thể biết chắc receiver đã commit hay chưa khi phản hồi bị mất.

Nhiều hệ thống thực tế dùng giao nhận at-least-once kết hợp idempotency/deduplication để đạt hiệu ứng gần với exactly-once trong một phạm vi xác định.

Phải nói rõ phạm vi bảo đảm:

- Một key chỉ duy nhất trong bảng idempotency nội bộ.
- Một event chỉ được consumer áp dụng một lần vào database nghiệp vụ.
- Một payment intent chỉ được nhà cung cấp thanh toán xử lý một lần theo chính sách key của họ.
- Một email có thể vẫn được gửi hai lần nếu dịch vụ email không hỗ trợ deduplication và worker mất phản hồi sau khi gửi.

Không có một UNIQUE constraint trong database có thể tự bảo đảm exactly-once cho mọi side effect xuyên qua nhiều hệ thống độc lập. Cần kết hợp transaction, outbox/inbox, key chống lặp ở từng ranh giới và cơ chế đối soát khi trạng thái không rõ ràng.

## 13. Thời hạn lưu idempotency key

Không nên xóa idempotency record quá sớm. Nếu record đã bị xóa nhưng client hoặc message vẫn được retry với key cũ, server có thể coi yêu cầu là mới và thực hiện lại.

Thời gian lưu cần dựa trên:

- Thời gian client có thể retry.
- Thời gian broker có thể redeliver message.
- Cửa sổ retry của gateway hoặc dịch vụ bên ngoài.
- Yêu cầu đối soát và điều tra nghiệp vụ.
- Quy định lưu trữ dữ liệu và dung lượng hệ thống.

Với payment hoặc thao tác tài chính, nên có một ràng buộc nghiệp vụ bền vững như `UNIQUE(order_id, payment_attempt)` hoặc một ledger không cho ghi trùng theo định danh giao dịch. Idempotency record có thể có thời hạn, nhưng bất biến tài chính quan trọng không nên phụ thuộc hoàn toàn vào cache key ngắn hạn.

Khi hết hạn, hệ thống cần xác định hành vi rõ ràng: key có thể được tái sử dụng, bị từ chối vĩnh viễn hay chỉ được dọn sau khi đã có một dấu vết nghiệp vụ lâu dài khác. Không nên để việc xóa dữ liệu deduplication vô tình mở đường tạo hiệu ứng lặp.

## 14. Retry an toàn sau timeout, deadlock và lỗi tạm thời

Retry chỉ có ý nghĩa khi phân loại được lỗi và giữ nguyên danh tính yêu cầu.

| Loại lỗi | Cách xử lý thường phù hợp |
|---|---|
| Timeout, không rõ server đã commit hay chưa | Gửi lại cùng idempotency key; đọc lại kết quả đã lưu |
| Deadlock victim | Rollback và retry toàn bộ transaction với cùng key nếu cùng một ý định nghiệp vụ |
| Serialization failure | Bắt đầu transaction mới, đọc và kiểm tra lại; không chỉ chạy lại câu ghi cuối |
| Mất kết nối trước khi server nhận request | Có thể gửi lại cùng key |
| Lỗi validation hoặc không đủ điều kiện nghiệp vụ | Không retry vô hạn; trả lỗi nghiệp vụ hoặc yêu cầu người dùng thay đổi request |
| Duplicate-key do cùng idempotency key | Đọc request record, so sánh hash và phát lại kết quả hoặc báo key đang xử lý |
| Cùng key nhưng payload khác | Từ chối vì một key không được đại diện cho hai ý định khác nhau |

Với lỗi tạm thời, có thể dùng exponential backoff và jitter:

```text
delay = min(max_delay, base_delay * 2^attempt)
wait(random(0, delay))
```

Giới hạn số lần retry và tổng thời gian retry. Nếu nhiều client retry cùng lúc với chu kỳ cố định, tải có thể dồn thành đợt; jitter giúp phân tán các lần thử.

Nếu client không nhận được phản hồi sau một khoảng thời gian, nó có thể truy vấn endpoint tra cứu trạng thái bằng cùng key thay vì liên tục gửi yêu cầu tạo mới.

## 15. Các nguyên tắc thiết kế thực tế

- Xác định một ý định nghiệp vụ và tạo một idempotency key cho ý định đó.
- Giữ nguyên key qua mọi lần retry của cùng yêu cầu.
- Định nghĩa phạm vi key bằng tenant, operation và các trường cần thiết.
- Đặt UNIQUE constraint/index trong database; không dựa vào `SELECT` kiểm tra trước.
- Tạo fingerprint từ payload đã chuẩn hóa và từ chối cùng key nhưng khác nội dung.
- Với hiệu ứng database, lưu idempotency record và kết quả nghiệp vụ trong cùng transaction.
- Với side effect bên ngoài, dùng key ở nhà cung cấp nếu có, transactional outbox và consumer deduplication.
- Lưu đủ kết quả để phát lại response có ý nghĩa; tránh lưu dữ liệu nhạy cảm không cần thiết.
- Quy định trạng thái `PROCESSING`, thời gian lease và cách phục hồi nếu dùng xử lý nhiều bước.
- Giữ deduplication record đủ lâu và bảo vệ bất biến nghiệp vụ dài hạn bằng constraint/ledger thích hợp.
- Chỉ retry lỗi tạm thời; dùng backoff, jitter và giới hạn số lần thử.

## 16. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Client gửi lại cùng JSON thì server tự biết đó là một request. | Server cần một định danh ổn định như idempotency key hoặc khóa nghiệp vụ để nhận diện cùng ý định. |
| Tạo key mới mỗi lần retry là an toàn. | Key mới khiến server có thể coi mỗi lần là một thao tác độc lập. |
| Chỉ cần lưu key sau khi xử lý xong. | Nếu thay đổi nghiệp vụ commit trước mà key chưa lưu, retry có thể tạo hiệu ứng lần hai. Hãy ghi cùng transaction khi có thể. |
| UNIQUE key có thể rollback email hoặc payment đã gửi. | Constraint chỉ bảo vệ database; side effect ngoài cần cơ chế chống lặp riêng. |
| Hai request trùng key luôn nhận cùng mã HTTP. | Có thể trả mã khác nhau nhưng cùng kết quả nghiệp vụ; hợp đồng API cần quy định rõ. |
| Idempotency key thay thế mọi constraint nghiệp vụ. | Nó chống lặp cùng request; các bất biến như một payment cho một order vẫn cần constraint riêng nếu nghiệp vụ yêu cầu. |
| Exactly-once có nghĩa message không bao giờ được giao hai lần. | Message vẫn có thể redeliver; consumer cần deduplicate để hiệu ứng không bị áp dụng lặp. |
| Xóa key cũ chỉ là dọn dữ liệu. | Xóa quá sớm có thể khiến retry cũ được thực hiện như yêu cầu mới. |

## 17. Tự kiểm tra

**Tình huống 1:** Server đã commit payment nhưng client timeout trước khi nhận response. Client nên làm gì khi retry?

**Đáp án:** Gửi lại cùng idempotency key và cùng payload. Server tìm record đã hoàn tất và trả lại payment/result cũ thay vì tạo payment mới.

**Tình huống 2:** Hai request cùng key và cùng payload đến đồng thời. Thành phần nào bảo vệ để chỉ một transaction tạo hiệu ứng nghiệp vụ?

**Đáp án:** UNIQUE constraint/index trên phạm vi key buộc hai transaction tranh chấp. Transaction giành quyền xử lý ghi kết quả nghiệp vụ và idempotency record trong cùng transaction; transaction còn lại đọc kết quả đã commit hoặc tiếp tục nếu transaction đầu rollback.

**Tình huống 3:** Cùng key được gửi lại nhưng amount khác. Server nên xử lý thế nào?

**Đáp án:** So sánh request hash/fingerprint và từ chối request vì cùng một key không được đại diện cho hai nội dung nghiệp vụ khác nhau.

**Tình huống 4:** Database đã commit đơn hàng và outbox event, nhưng worker chết sau khi publish event trước khi đánh dấu đã gửi. Điều gì có thể xảy ra?

**Đáp án:** Worker có thể publish lại cùng event. Consumer cần lưu event id đã xử lý và cập nhật dữ liệu nghiệp vụ trong cùng transaction để lần giao lại không tạo hiệu ứng lần hai.

**Tình huống 5:** Có thể bảo đảm email được gửi đúng một lần chỉ bằng idempotency key trong database không?

**Đáp án:** Không. Database không thể rollback hoặc xác nhận chắc chắn side effect ở dịch vụ email. Cần idempotency/deduplication ở dịch vụ nhận nếu hỗ trợ, outbox và cơ chế đối soát; nếu nhà cung cấp không hỗ trợ deduplication, vẫn có thể có trường hợp gửi lặp khi mất phản hồi.

**Tình huống 6:** Khi nào một idempotency record có thể được xóa?

**Đáp án:** Sau cửa sổ retry/redelivery đã xác định và khi hệ thống vẫn có một ràng buộc hoặc dấu vết nghiệp vụ đủ bền để ngăn thao tác tài chính quan trọng bị tạo lại. Thời hạn phải theo hợp đồng API và yêu cầu lưu trữ, không xóa tùy tiện.

Khi thiết kế retry, hãy bắt đầu từ câu hỏi: nếu server đã thực hiện xong nhưng phản hồi bị mất, lần gửi tiếp theo có nhận ra cùng một ý định nghiệp vụ không? Một idempotency key ổn định, UNIQUE constraint và kết quả được lưu nguyên tử cùng thay đổi database tạo nền tảng cho câu trả lời đó. Với side effect bên ngoài, phải mở rộng cơ chế chống lặp qua từng ranh giới hệ thống.
