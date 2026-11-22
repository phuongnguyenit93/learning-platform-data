# Thực thi lại thao tác có tác động bên ngoài mà thiếu tính lũy đẳng

Retry giúp một thao tác phục hồi sau lỗi tạm thời, nhưng nó trở nên nguy hiểm khi thao tác có tác động bên ngoài database và không có tính lũy đẳng (*idempotency*). Ví dụ, một request thanh toán đã được nhà cung cấp xử lý nhưng response bị mất. Ứng dụng chỉ thấy timeout và gửi lại request. Nếu lần gửi lại tạo một khoản thu mới, khách hàng có thể bị tính tiền hai lần dù transaction database của ứng dụng chỉ commit một lần.

Vấn đề cốt lõi là **rollback database không thể hoàn tác một tác dụng phụ đã xảy ra ở hệ thống khác**. Một lần timeout cũng không chứng minh hệ thống nhận chưa thực hiện request. Nếu ứng dụng retry như thể lần trước chắc chắn thất bại, nó có thể nhân đôi thanh toán, gửi email, tạo shipment, phát message hoặc cấp quyền.

Muốn retry an toàn, cần nhận diện một ý định nghiệp vụ ổn định qua mọi attempt, bảo vệ tác dụng bằng idempotency key hoặc cơ chế dedup ở hệ thống nhận, lưu trạng thái để phục hồi sau crash và phân biệt kết quả thất bại chắc chắn với kết quả chưa xác định. Nếu hệ thống bên ngoài không hỗ trợ idempotency, cần cơ chế tra cứu/đối soát hoặc quy trình bù trừ; không thể dùng transaction cục bộ để tạo bảo đảm exactly-once cho một HTTP call.

## 1. Idempotency là gì?

Một thao tác là **lũy đẳng** (*idempotent*) nếu thực hiện một lần hay lặp lại nhiều lần với cùng ý định và cùng dữ liệu đều dẫn đến cùng trạng thái hiệu lực cuối cùng.

Ví dụ:

- `PUT /users/42/email` đặt email của user 42 thành một giá trị cụ thể có thể lũy đẳng nếu mỗi lần gọi đều đặt cùng giá trị.
- `DELETE /sessions/abc` có thể lũy đẳng nếu xóa một session đã bị xóa vẫn để trạng thái cuối là “không tồn tại”.
- `POST /payments` tạo một khoản thanh toán mới thường không tự lũy đẳng: mỗi lần gọi có thể tạo một payment khác.
- `balance = balance + 10` không lũy đẳng: gọi hai lần làm số dư tăng 20.
- `sendEmail()` thường không lũy đẳng: gọi hai lần có thể gửi hai email.

Theo nghĩa toán học, một hàm `f` là idempotent nếu:

\[
f(f(x)) = f(x)
\]

Trong hệ thống phân tán, ta quan tâm đến hiệu lực nghiệp vụ: cùng một ý định thanh toán chỉ được thu tiền một lần; cùng một sự kiện không tạo hai shipment; cùng một lệnh cấp quyền không tạo hai lần ghi nhận. Kết quả response có thể được trả lại nhiều lần, nhưng tác dụng nghiệp vụ chỉ được áp dụng một lần.

### Idempotency khác với deduplication

Hai khái niệm liên quan nhưng khác nhau:

- **Idempotency:** lặp lại cùng một thao tác không làm thay đổi thêm trạng thái hiệu lực.
- **Deduplication:** nhận diện hai lần gửi/giao có cùng định danh để bỏ qua lần lặp.

Một idempotency key thường được dùng để thực hiện deduplication và tạo hành vi lũy đẳng cho API. Nhưng dedup chỉ có ý nghĩa nếu định danh ổn định, phạm vi duy nhất đúng và record được lưu đủ lâu.

## 2. Vì sao retry thao tác bên ngoài dễ tạo tác dụng phụ trùng?

Database transaction có thể bảo đảm các thay đổi trong cùng database cùng commit hoặc cùng rollback. Một HTTP call, email hoặc lệnh gửi tới broker là một hành động ở hệ thống khác, không nằm trong transaction cục bộ đó.

### Trường hợp A: tác dụng bên ngoài thành công, database rollback

```text
BEGIN database transaction
  ghi order ở trạng thái PENDING
  gọi payment provider -> provider thu tiền thành công
  cập nhật order thành PAID
  lỗi database xảy ra
ROLLBACK
```

Database trở lại trạng thái trước transaction, nhưng provider không hoàn tác khoản tiền đã thu. Ứng dụng có thể thấy order vẫn `PENDING` trong khi tiền đã bị thu.

### Trường hợp B: database commit, tác dụng bên ngoài chưa được gửi

```text
BEGIN database transaction
  ghi order thành PAID
COMMIT
process crash
gửi email xác nhận chưa xảy ra
```

Đơn hàng đã được commit nhưng thông báo không được gửi. Nếu ứng dụng chỉ dựa vào code chạy ngay sau commit, không có cơ chế bền vững nào bảo đảm công việc đó được tiếp tục sau crash.

### Trường hợp C: provider thành công nhưng response bị mất

```text
Client -> Payment API: charge 500.000 VND
Payment API: tạo charge và commit thành công
Network: response bị mất hoặc timeout
Client: không biết charge đã thành công hay chưa
Client: gửi lại request
Payment API: tạo charge thứ hai
```

Đây là **ambiguous outcome** (*kết quả chưa xác định*). Caller không biết request đầu đã được thực hiện hay chưa. Retry bằng một request ID mới có thể tạo tác dụng phụ thứ hai.

### Bảng các cửa sổ lỗi

| Thời điểm lỗi | Điều caller biết | Rủi ro nếu retry mù |
|---|---|---|
| Chắc chắn request chưa được gửi ra mạng | Hệ thống nhận chưa thể xử lý request đó | Retry thường an toàn nếu chưa có tác dụng nào khác. |
| Request đã gửi, chưa nhận response | Không biết hệ thống nhận đã xử lý hay chưa | Có thể tạo tác dụng phụ trùng. |
| Hệ thống nhận trả thành công nhưng caller mất response | Tác dụng đã xảy ra, caller không biết | Retry không có key có thể thực hiện lần thứ hai. |
| Provider trả lỗi xác nhận không thực hiện | Có bằng chứng thao tác chưa xảy ra | Có thể thử lại nếu lỗi được phân loại là tạm thời. |
| Database commit thành công nhưng process crash trước khi ghi nhận kết quả ở tầng ứng dụng | Kết quả bền vững có thể đã tồn tại | Cần tra cứu theo operation ID hoặc idempotency key. |

Timeout chỉ nói rằng caller không nhận kết quả đúng hạn. Nó không nói rằng hệ thống bên kia chưa thực hiện thao tác.

## 3. Anti-pattern: gọi dịch vụ ngoài trong transaction rồi retry toàn bộ method

Một cách triển khai dễ mắc lỗi:

```java
@Transactional
public void placeOrder(Order order) {
    orderRepository.insert(order);
    paymentClient.charge(order.total());
    inventoryRepository.reserve(order.items());
    orderRepository.markPaid(order.id());
}
```

Giả sử `paymentClient.charge()` thành công, nhưng `inventoryRepository.reserve()` gặp deadlock. Transaction database rollback. Nếu retry policy gọi lại toàn bộ `placeOrder()`, payment provider có thể thu tiền lần thứ hai.

Ngay cả khi không có retry, việc giữ transaction và connection trong lúc chờ HTTP cũng làm transaction dài, giữ tài nguyên lâu và tăng nguy cơ lock wait/pool exhaustion.

### Vì sao rollback không giải quyết được?

`@Transactional` chỉ quản lý tài nguyên được transaction manager hỗ trợ, chẳng hạn JDBC connection hoặc JPA persistence context. Nó không thể tự rollback:

- Một khoản tiền đã thu ở payment provider.
- Một email đã được SMTP/provider gửi.
- Một shipment đã được hãng vận chuyển tạo.
- Một message đã được broker nhận và consumer đã xử lý.
- Một quyền truy cập đã được cấp trong hệ thống identity bên ngoài.

Các hệ thống đó có transaction và trạng thái riêng. Muốn phối hợp cần idempotency, outbox/inbox, saga hoặc một giao thức phân tán được hỗ trợ rõ ràng.

## 4. Idempotency key phải đại diện cho ý định nghiệp vụ

Một **idempotency key** là định danh ổn định cho một lần thực hiện nghiệp vụ. Mọi lần gửi lại cùng ý định phải dùng lại đúng key đó.

Ví dụ:

```text
Ý định nghiệp vụ: thu 500.000 VND cho order-5001
Idempotency key: payment-order-5001-attempt-1

Attempt 1 -> key payment-order-5001-attempt-1
Attempt 2 -> key payment-order-5001-attempt-1
Attempt 3 -> key payment-order-5001-attempt-1
```

Nếu attempt 1 đã được provider xử lý nhưng response bị mất, attempt 2 với cùng key cho phép provider nhận ra đây là cùng ý định và trả lại kết quả đã lưu thay vì tạo charge mới, nếu provider thực hiện đúng hợp đồng idempotency.

### Không tạo key mới cho mỗi lần retry

Đây là lỗi phổ biến:

```java
for (int attempt = 1; attempt <= 3; attempt++) {
    String key = UUID.randomUUID().toString(); // Sai cho cùng một ý định.
    paymentClient.charge(key, amount);
}
```

Mỗi lần lặp có một key mới nên provider xem chúng là các yêu cầu độc lập. Key cần được tạo một lần cho logical operation rồi lưu bền vững trước khi bắt đầu lời gọi có thể gây tác dụng phụ.

### Key không được dùng chung cho các ý định khác nhau

Ngược lại, không dùng một key chung cho mọi lần thanh toán của một order nếu nghiệp vụ cho phép nhiều payment attempt thực sự. Ví dụ lần thử thanh toán bằng thẻ A thất bại chắc chắn, sau đó khách chọn thẻ B và tạo một payment attempt mới. Đó có thể là ý định mới và cần key mới.

Một quy tắc thực tế:

- Retry cùng một lần thu tiền: giữ nguyên key.
- Tạo một lần thu tiền mới theo quyết định nghiệp vụ mới: tạo key mới.
- Hoàn tiền là một tác dụng nghiệp vụ riêng: dùng refund operation ID/key riêng.
- Gửi lại cùng một webhook/event: giữ nguyên event ID.

Key nên gắn với danh tính của tác dụng nghiệp vụ cụ thể, không gắn với số lần thread chạy hoặc số lần HTTP client thử kết nối.

## 5. Lưu idempotency key và kết quả ở phía server

API có thể lưu một record cho mỗi key để xử lý request trùng. Schema minh họa:

```sql
CREATE TABLE idempotency_records (
    scope VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(24) NOT NULL,
    response_code INTEGER,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (scope, idempotency_key)
);
```

`scope` xác định phạm vi duy nhất, chẳng hạn tenant, merchant hoặc loại operation. `request_hash` giúp phát hiện cùng key bị dùng với payload khác. `status` mô tả tiến trình xử lý; `response_code` và `response_body` cho phép trả lại kết quả đã lưu.

### Quy trình xử lý request

Một API có thể thực hiện các bước:

1. Nhận idempotency key từ caller.
2. Chuẩn hóa payload và tính request hash.
3. Thử claim key bằng insert có unique constraint.
4. Nếu key đã tồn tại, so sánh request hash.
5. Nếu hash khác, trả lỗi conflict vì cùng key được dùng cho nội dung khác.
6. Nếu operation đã hoàn tất, trả lại kết quả đã lưu.
7. Nếu operation đang chạy, trả trạng thái đang xử lý hoặc cho caller chờ/tra cứu theo hợp đồng API.
8. Nếu key mới, xử lý operation và lưu kết quả theo transaction phù hợp.

Kiểm tra bằng `SELECT` trước khi `INSERT` không đủ để phân xử hai request đồng thời. Cả hai request có thể cùng thấy key chưa tồn tại. Unique constraint trên `(scope, idempotency_key)` phải là cơ chế quyết định.

### Cùng key nhưng payload khác phải bị từ chối

Ví dụ caller gửi:

```text
Key: K-123
Payload lần đầu: order=5001, amount=500000 VND
Payload lần sau: order=5002, amount=900000 VND
```

Nếu server chỉ tra key rồi trả kết quả cũ mà không kiểm tra payload, caller có thể nhận kết quả của một thao tác khác và gây nhầm lẫn nghiêm trọng. Nếu server thực hiện payload mới, nó phá vỡ ý nghĩa idempotency key.

Hãy so sánh request hash hoặc các trường nghiệp vụ bất biến. Cùng key với nội dung khác nên trả lỗi rõ ràng, thường là conflict/invalid idempotency key theo hợp đồng API.

## 6. Xử lý request trùng đến đồng thời

Hai request có cùng key có thể đến hai instance ứng dụng cùng lúc. Cả hai không được cùng tạo tác dụng bên ngoài.

```text
Request A                         Request B
---------                         ---------
INSERT key K -> thành công
                                  INSERT key K -> conflict/chờ
thực hiện operation
lưu kết quả
COMMIT
                                  đọc record đã hoàn tất
                                  trả kết quả đã lưu
```

Unique constraint giúp chỉ một request claim được key. Request còn lại cần xử lý duplicate theo trạng thái record.

Nếu operation rất ngắn và tác dụng nằm hoàn toàn trong cùng database, có thể claim key và cập nhật nghiệp vụ trong một transaction. Nhưng nếu cần gọi provider bên ngoài, không giữ transaction database mở trong suốt thời gian chờ provider. Dùng một operation record có trạng thái và worker xử lý riêng.

### Trạng thái operation dài hạn

Một state machine có thể là:

```text
NEW -> IN_PROGRESS -> SUCCEEDED
             |
             +------> FAILED_FINAL
             |
             +------> UNKNOWN / RECONCILIATION_REQUIRED
```

- `NEW`: ý định đã được lưu, chưa gửi ra ngoài.
- `IN_PROGRESS`: worker đang xử lý, thường có lease/owner.
- `SUCCEEDED`: đã có kết quả xác nhận và lưu bền vững.
- `FAILED_FINAL`: provider xác nhận thất bại không thể retry theo chính sách.
- `UNKNOWN`: request có thể đã được thực hiện nhưng chưa có kết quả chắc chắn.
- `RECONCILIATION_REQUIRED`: cần tra cứu provider hoặc xử lý thủ công trước khi gửi lại.

Không đánh dấu `FAILED_FINAL` chỉ vì caller timeout. Timeout sau khi request được gửi thường phải được xem là kết quả chưa xác định cho đến khi có bằng chứng.

## 7. Tận dụng idempotency của provider bên ngoài

Nhiều API thanh toán và dịch vụ hỗ trợ idempotency key, nhưng hợp đồng cụ thể khác nhau. Trước khi dựa vào nó, cần đọc tài liệu của provider và xác nhận:

- Key được truyền ở header hay field nào.
- Phạm vi duy nhất của key: account, merchant, endpoint hay toàn provider.
- Thời gian provider lưu key và kết quả.
- Cùng key nhưng payload khác được xử lý thế nào.
- Request đồng thời cùng key có được tuần tự hóa không.
- Response duplicate là response gốc, trạng thái hiện tại hay một mã conflict.
- Những loại lỗi nào được lưu vào idempotency record.
- Có API tra cứu operation bằng key hoặc merchant reference không.

Ví dụ khái niệm:

```http
POST /payments
Idempotency-Key: payment-order-5001-attempt-1
Content-Type: application/json

{
  "orderId": "order-5001",
  "amount": 500000,
  "currency": "VND"
}
```

Khi timeout, lần gửi lại phải giữ nguyên `Idempotency-Key` và payload. Không tự giả định provider giữ key vĩnh viễn. Nếu key hết hạn sau một khoảng thời gian, retry muộn có thể bị xem là operation mới. Lưu thời điểm tạo key và thiết kế reconciliation phù hợp với thời hạn provider.

### Idempotency của provider không thay thế trạng thái nội bộ

Ngay cả khi provider hỗ trợ key, ứng dụng vẫn cần lưu operation ID, key, payload hash, trạng thái và provider reference. Nếu process crash, worker sau phải biết cần dùng lại key nào và phải tra cứu operation nào.

Không tạo key chỉ trong biến local rồi hy vọng retry sau restart vẫn dùng lại được. Key cần được lưu cùng ý định nghiệp vụ trong database hoặc một kho bền vững khác trước khi thực hiện side effect.

## 8. Dùng transactional outbox để lưu ý định gọi bên ngoài

Một cách an toàn để tách database transaction khỏi HTTP call là **transactional outbox**. Trong cùng transaction, ứng dụng cập nhật dữ liệu nghiệp vụ và ghi một command/event vào bảng outbox. Worker riêng đọc outbox sau commit và thực hiện lời gọi bên ngoài.

Ví dụ khi tạo order cần thu tiền:

```sql
BEGIN;

INSERT INTO orders (id, status, total_amount)
VALUES (:orderId, 'PENDING_PAYMENT', :amount);

INSERT INTO payment_operations (
    operation_id, order_id, idempotency_key,
    request_hash, status, created_at
)
VALUES (
    :operationId, :orderId, :stableKey,
    :requestHash, 'NEW', CURRENT_TIMESTAMP
);

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload, created_at
)
VALUES (
    :eventId, :orderId, 'ChargePaymentRequested', :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
```

Sau commit, worker đọc command và gọi payment provider bằng idempotency key đã lưu. Khi nhận kết quả, worker mở transaction mới để cập nhật `payment_operations`, `orders` và ghi event kết quả vào outbox nếu cần.

Lợi ích là trạng thái order, payment operation và ý định gọi provider được lưu cùng nhau. Nếu process crash ngay sau commit nhưng trước khi gọi provider, outbox vẫn còn để worker khác tiếp tục.

### Outbox publisher vẫn có thể gửi trùng

Outbox không làm việc gửi ra ngoài exactly-once. Một worker có thể:

1. Gửi request tới provider thành công.
2. Provider tạo charge.
3. Worker crash trước khi đánh dấu outbox đã gửi.
4. Worker khác đọc lại outbox và gửi lại.

Vì vậy, worker phải dùng cùng idempotency key cho cùng operation. Nếu hệ thống nhận là broker, consumer cần inbox/dedup. Nếu provider không hỗ trợ idempotency hoặc tra cứu, outbox chỉ bảo đảm ý định được thử lại; nó không tự ngăn tác dụng phụ trùng.

### Không giữ transaction khi gọi provider

Worker nên claim command bằng một transaction ngắn, commit trạng thái/lease, gọi provider ngoài transaction, rồi mở transaction khác để lưu kết quả. Không giữ row lock và connection trong suốt thời gian HTTP request.

Lease cần có timeout để worker khác phục hồi nếu worker cũ chết. Nếu lease hết hạn trong khi worker cũ vẫn chạy, cả hai có thể cùng gọi provider; stable idempotency key ở provider là lớp bảo vệ quan trọng. Có thể dùng fencing token/version để ngăn worker cũ ghi đè trạng thái mới ở database.

## 9. Kết hợp inbox ở phía nhận

Nếu tác dụng phụ được phát thành message tới broker, consumer nên dùng inbox pattern:

1. Nhận event với `event_id` ổn định.
2. Trong transaction database, insert inbox record có unique key.
3. Nếu event mới, thực hiện business update cùng transaction.
4. Commit database.
5. Sau commit mới ACK broker.

Nếu consumer crash sau commit nhưng trước ACK, broker giao lại event. Unique constraint trong inbox giúp nhận diện duplicate và không áp dụng business update lần thứ hai.

Inbox bảo vệ các thay đổi nằm trong cùng database transaction. Nếu consumer tiếp tục gọi một API ngoài, gửi email hoặc tạo shipment, tác dụng phụ đó vẫn cần idempotency riêng hoặc outbox tiếp theo.

## 10. Khi provider không hỗ trợ idempotency

Không phải dịch vụ ngoài nào cũng cung cấp idempotency key. Ví dụ SMTP truyền thống không có cơ chế chung để bảo đảm một email chỉ được gửi đúng một lần; một API cũ có thể chỉ nhận `POST` tạo mới và không cho tra cứu theo client reference.

Trong trường hợp đó, cần đánh giá khả năng tra cứu và mức rủi ro:

### Dùng client reference duy nhất

Nếu provider cho phép gửi một merchant reference hoặc external reference, hãy tạo giá trị ổn định cho logical operation và dùng nó để tra cứu sau timeout. Nếu provider có unique constraint trên reference, nó có thể đóng vai trò dedup. Cần xác minh đây là bảo đảm thực sự của provider, không chỉ là trường metadata tự do.

### Tra cứu trước khi gửi lại

Khi kết quả chưa xác định, gọi API tra cứu theo reference để xem operation đã tồn tại hay chưa. Nếu tìm thấy thành công, cập nhật nội bộ theo kết quả đó. Nếu provider trả “không tìm thấy”, chỉ retry khi hợp đồng tra cứu bảo đảm kết quả đủ nhất quán và không có độ trễ indexing có thể khiến operation vừa tạo chưa xuất hiện.

### Đối soát định kỳ

Với payment hoặc shipment, có thể đối soát operation nội bộ với báo cáo/provider API. Các record `UNKNOWN` quá lâu được đưa vào reconciliation queue. Không tự động gửi một charge mới chỉ vì chưa thấy response.

### Chấp nhận at-least-once hoặc at-most-once theo nghiệp vụ

Nếu không thể dedup và không thể tra cứu, phải lựa chọn rõ:

- Retry để ưu tiên không mất thao tác, chấp nhận nguy cơ trùng.
- Không retry để ưu tiên không tạo tác dụng phụ thứ hai, chấp nhận nguy cơ thao tác đầu chưa xảy ra.

Đây là tradeoff nghiệp vụ, không phải vấn đề có thể giải quyết chỉ bằng cách tăng timeout. Với thanh toán, email hoặc hành động có chi phí cao, thường cần quy trình đối soát hoặc can thiệp thay vì quyết định tự động dựa trên timeout.

## 11. Compensation không phải rollback

Trong quy trình nhiều dịch vụ, **saga** dùng các hành động bù trừ (*compensating actions*) để xử lý khi một bước sau thất bại. Ví dụ:

```text
Tạo order
   -> Thu tiền
      -> Giữ hàng
         -> Tạo shipment
```

Nếu tạo shipment thất bại sau khi đã thu tiền, hệ thống có thể phát lệnh refund. Refund là một tác dụng nghiệp vụ mới, có thể thất bại hoặc chờ xử lý; nó không xóa lịch sử charge như thể charge chưa từng xảy ra.

Một saga cần:

- Trạng thái bền vững cho từng bước.
- ID ổn định cho từng command/operation.
- Idempotency cho cả hành động tiến và hành động bù trừ.
- Retry có giới hạn và trạng thái `UNKNOWN` khi kết quả chưa xác định.
- Reconciliation khi provider phản hồi chậm hoặc kết quả không thể xác định.
- Theo dõi và cảnh báo các saga bị kẹt.

Không gọi refund tự động nhiều lần với key mới sau timeout. Refund cũng là một side effect và cần idempotency key riêng cho cùng một refund intent.

## 12. Thiết kế state machine cho external operation

Một operation bên ngoài nên có trạng thái rõ ràng thay vì chỉ có boolean `sent`:

```text
NEW
 |
 v
IN_PROGRESS
 |       \
 |        \ timeout / mất kết nối sau khi gửi
 |         v
 |       UNKNOWN
 |         |
 |         +---- tra cứu provider ----> SUCCEEDED
 |         |
 |         +---- xác nhận thất bại ---> FAILED_FINAL
 |         |
 |         +---- chưa rõ ------------> RECONCILIATION_REQUIRED
 |
 +---- provider xác nhận thành công -> SUCCEEDED
 |
 +---- lỗi permanent ---------------> FAILED_FINAL
 |
 +---- lỗi transient chắc chắn ------> RETRY_WAIT
                                         |
                                         v
                                      IN_PROGRESS
```

Không nên chuyển `UNKNOWN` thẳng về `NEW` và tạo key mới. Phải tra cứu hoặc tiếp tục với cùng idempotency key theo hợp đồng provider.

Một schema có thể lưu:

```sql
CREATE TABLE external_operations (
    operation_id VARCHAR(120) PRIMARY KEY,
    business_reference VARCHAR(160) NOT NULL,
    provider VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    provider_reference VARCHAR(160),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code VARCHAR(80),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_provider_idempotency
        UNIQUE (provider, idempotency_key)
);
```

Các trạng thái và unique scope cần điều chỉnh theo provider. Không nên giả định một provider key chỉ duy nhất toàn hệ thống nếu hợp đồng chỉ bảo đảm trong merchant account hoặc endpoint.

## 13. Java: giữ key ổn định qua các lần thử

Một ví dụ đơn giản cho thấy key phải được tạo trước vòng retry và được lưu bền vững:

```java
public PaymentResult charge(PaymentOperation operation) {
    // operation.idempotencyKey đã được lưu cùng operation trước đó.
    String key = operation.idempotencyKey();

    for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
        try {
            return paymentProvider.charge(
                key,
                operation.amount(),
                operation.currency(),
                operation.orderReference()
            );
        } catch (DefinitelyNotProcessedException ex) {
            if (attempt == MAX_ATTEMPTS) {
                throw ex;
            }
            backoffWithJitter(attempt);
        } catch (AmbiguousOutcomeException ex) {
            return reconcileOrRetrySameKey(operation, ex);
        }
    }

    throw new IllegalStateException("Unreachable");
}
```

Đây là khung minh họa, không phải implementation đầy đủ. `DefinitelyNotProcessedException` chỉ được dùng khi client có bằng chứng request chưa được thực hiện. `AmbiguousOutcomeException` cần tra cứu provider hoặc retry cùng key theo hợp đồng idempotency. Không tạo key mới trong vòng lặp.

### Đừng retry toàn bộ use case một cách mù quáng

Tách phần transaction database có thể retry khỏi external operation đã có định danh và trạng thái riêng. Nếu database transaction thất bại sau khi provider đã thành công, lần chạy lại phải tra cứu hoặc tái sử dụng cùng operation/key, không tạo payment mới.

Một kiến trúc có thể là:

```text
PlaceOrder use case
  ├─ Transaction A: tạo order + payment operation + outbox
  ├─ Commit
  └─ Payment worker
       ├─ gọi provider với stable idempotency key
       └─ Transaction B: lưu kết quả + cập nhật order + outbox result
```

Hai transaction database có ranh giới rõ ràng. Worker có thể chạy lại sau crash mà vẫn dùng cùng external operation identity.

## 14. Retry chỉ lỗi phù hợp và phải có giới hạn

Idempotency giúp tránh lặp tác dụng phụ, nhưng không có nghĩa nên retry mọi lỗi vô hạn.

| Loại lỗi | Cách xử lý thường phù hợp |
|---|---|
| Validation/authentication error | Không retry cùng request; sửa dữ liệu hoặc credential. |
| Provider từ chối nghiệp vụ (ví dụ không đủ tiền) | Ghi kết quả thất bại cuối theo hợp đồng; không retry mù. |
| Rate limit có `Retry-After` | Có thể retry cùng key sau thời điểm cho phép nếu còn deadline. |
| Lỗi kết nối chắc chắn xảy ra trước khi gửi request | Có thể retry cùng key. |
| Timeout sau khi request có thể đã tới provider | Xem là `UNKNOWN`; tra cứu hoặc retry cùng key nếu provider bảo đảm idempotency. |
| Provider `5xx` | Không tự suy ra thao tác chưa xảy ra; kiểm tra hợp đồng và dùng cùng key/tra cứu. |
| Database deadlock khi lưu kết quả provider | Retry transaction database mới; không tạo external operation mới. |
| Idempotency key reused with different payload | Dừng và báo lỗi; không retry cùng payload sai hoặc tạo key mới tự động. |

Chính sách retry cần có:

- Số attempt tối đa.
- Deadline tổng và timeout mỗi attempt.
- Exponential backoff có jitter.
- Phân loại lỗi transient/permanent/ambiguous.
- Cùng key cho cùng logical side effect.
- Reconciliation cho kết quả chưa xác định.
- Metric và cảnh báo cho operation bị kẹt hoặc hết ngân sách.

## 15. Thời hạn lưu idempotency record

Idempotency chỉ bảo vệ trong khoảng thời gian record còn tồn tại và provider còn ghi nhớ key. Nếu ứng dụng xóa record sau một ngày nhưng message có thể được replay sau một tuần, cùng event có thể được xử lý lại.

Thời hạn lưu cần dựa trên:

- Thời gian retry tối đa của client và worker.
- Thời gian message có thể nằm trong broker hoặc DLQ.
- Cửa sổ replay vận hành.
- Thời hạn provider lưu idempotency key.
- Thời gian đối soát và khiếu nại nghiệp vụ.
- Hậu quả nếu tác dụng phụ bị lặp.

Với payment/ledger, có thể cần một khóa nghiệp vụ bền vững lâu hơn cache idempotency ngắn hạn. Ví dụ unique constraint trên `(order_id, payment_attempt_id)` hoặc `provider_reference` có thể ngăn tạo ledger entry trùng trong phạm vi domain.

Không xóa idempotency record chỉ để giải phóng dung lượng mà chưa có chính sách archive/retention và kiểm soát replay. Nếu provider hết thời gian lưu key, không gửi lại operation cũ một cách tự động trước khi tra cứu trạng thái.

## 16. Đo lường và quan sát external retry

Cần theo dõi logical operation và attempt riêng. Các metric hữu ích:

- Số external operations được tạo.
- Số attempt gửi tới provider.
- Số duplicate request được provider deduplicate.
- Số operation ở trạng thái `UNKNOWN`.
- Số operation cần reconciliation.
- Số operation thành công sau retry.
- Số operation hết attempt/deadline.
- Thời gian từ `NEW` đến `SUCCEEDED`.
- Tuổi của operation `IN_PROGRESS` hoặc `UNKNOWN` lâu bất thường.
- Số lần idempotency key được gửi lại và kết quả tương ứng.
- Số mismatch payload hash cho cùng key.

Log/trace nên có operation ID, idempotency key đã che một phần nếu cần, provider reference, attempt number, error class, request hash và correlation ID. Không ghi card number, secret, access token hoặc payload nhạy cảm.

Dashboard cần tách lỗi provider khỏi lỗi lưu database. Ví dụ provider charge thành công nhưng transaction cập nhật order thất bại là một tình huống khác với provider từ chối charge. Nếu gộp cả hai thành `payment_failed`, đội vận hành có thể gửi lại charge và tạo khoản thu trùng.

## 17. Kiểm thử các cửa sổ lỗi

Một test happy path không chứng minh retry an toàn. Cần mô phỏng crash/timeout ở các điểm có thể làm caller không biết kết quả.

### Provider thành công, response bị mất

1. Fake provider nhận key `K`, ghi nhận charge thành công.
2. Fake provider cố ý đóng kết nối hoặc trả timeout sau khi đã ghi nhận tác dụng.
3. Worker retry cùng key `K`.
4. Fake provider trả lại kết quả của charge ban đầu.
5. Xác nhận chỉ có một charge trong provider ledger.

### Provider thành công, worker crash trước khi lưu kết quả

1. Worker gửi request với key `K`.
2. Provider tạo charge.
3. Worker dừng trước transaction lưu `SUCCEEDED`.
4. Lease hết hạn và worker khác claim operation.
5. Worker mới tra cứu hoặc gửi lại cùng key `K`.
6. Xác nhận không có charge thứ hai và database cuối cùng ghi nhận provider reference đúng.

### Hai request cùng idempotency key đến đồng thời

1. Gửi hai request cùng scope, key và payload.
2. Đồng bộ để cả hai cùng claim gần như đồng thời.
3. Xác nhận unique constraint chỉ cho một operation được tạo.
4. Request còn lại nhận kết quả hiện có hoặc trạng thái đang xử lý.
5. Xác nhận provider chỉ thực hiện một side effect.

### Cùng key nhưng payload khác

Gửi cùng key với amount hoặc order reference khác. Xác nhận server trả conflict và không tạo operation thứ hai.

### Database rollback sau external success

Cho provider thành công rồi cố ý làm transaction cập nhật kết quả thất bại. Xác nhận operation chuyển sang trạng thái cần reconciliation/retry cùng key; không tạo key mới.

### Outbox publish trùng

Cho worker gửi message thành công rồi crash trước khi đánh dấu outbox published. Sau redelivery, xác nhận consumer inbox hoặc provider idempotency ngăn business effect lặp.

Test nên dùng fake provider có ledger và idempotency behavior rõ ràng, đồng thời có integration test với provider sandbox khi hợp đồng bên ngoài cần được xác minh.

## 18. Những sai lầm thường gặp

- **Tạo idempotency key mới cho mỗi retry:** provider coi mỗi attempt là một operation mới và có thể tạo charge/email/shipment trùng.
- **Gọi dịch vụ ngoài bên trong transaction rồi retry toàn method:** database rollback không hoàn tác side effect bên ngoài.
- **Xem timeout là thất bại chắc chắn:** request có thể đã được thực hiện; kết quả phải được xem là chưa xác định.
- **Đánh dấu operation failed ngay khi mất kết nối:** có thể provider đã thành công và response bị mất.
- **Dùng cùng key cho payload khác:** có thể trả nhầm kết quả hoặc phá vỡ hợp đồng idempotency.
- **Kiểm tra key bằng SELECT rồi INSERT:** hai request đồng thời có thể cùng vượt qua; cần unique constraint và insert-if-absent nguyên tử.
- **Chỉ lưu key trong memory:** process restart làm mất key và retry sau đó tạo operation mới.
- **Cho rằng outbox tự bảo đảm exactly-once:** publisher có thể gửi trùng sau crash; consumer/provider vẫn cần dedup.
- **Cho rằng inbox bảo vệ HTTP call tiếp theo:** inbox chỉ bảo vệ các thay đổi trong cùng database transaction.
- **Dùng refund như rollback:** refund là side effect mới, cũng có thể timeout hoặc bị lặp.
- **Xóa record idempotency quá sớm:** replay hoặc retry muộn có thể tạo tác dụng lần nữa.
- **Retry mọi lỗi:** lỗi nghiệp vụ/permanent không biến mất khi gửi lại; retry có thể tăng tải và side effect.
- **Không đối soát trạng thái UNKNOWN:** operation có thể bị kẹt giữa “đã thực hiện” và “chưa được ghi nhận”.

## 19. Quy trình thiết kế retry an toàn cho một side effect

Trước khi cho phép retry một thao tác bên ngoài, hãy trả lời:

1. Tác dụng phụ chính xác là gì: charge, refund, email, shipment, cấp quyền hay phát message?
2. Logical operation ID nào đại diện cho một ý định nghiệp vụ?
3. Idempotency key được tạo và lưu ở đâu trước lần gọi đầu tiên?
4. Provider có hỗ trợ idempotency không; key scope, retention và payload matching ra sao?
5. Nếu provider không hỗ trợ, có merchant reference hoặc API tra cứu nào đủ tin cậy không?
6. Những lỗi nào chứng minh request chưa được xử lý, lỗi nào có kết quả chưa xác định?
7. Khi timeout sau khi gửi, hệ thống tra cứu hay gửi lại cùng key theo chính sách nào?
8. Hai request đồng thời cùng key được phân xử bằng unique constraint nào?
9. Trạng thái `IN_PROGRESS`, `UNKNOWN`, `SUCCEEDED` và `FAILED_FINAL` được lưu ra sao?
10. Database transaction nào lưu ý định, kết quả và outbox?
11. Retry có bounded attempts, deadline, backoff và jitter không?
12. Nếu worker crash sau side effect nhưng trước khi lưu kết quả, worker sau phục hồi thế nào?
13. Inbox/provider dedup có bảo vệ các lần giao lại không?
14. Record được lưu bao lâu và replay/DLQ được xử lý thế nào?
15. Nếu không thể biết kết quả, ai hoặc quy trình nào thực hiện reconciliation?

Nếu không thể trả lời câu hỏi về định danh ổn định và kết quả chưa xác định, không nên tự động retry một side effect có chi phí hoặc hậu quả lớn. Hãy bổ sung cơ chế tra cứu, idempotency hoặc quy trình xử lý thủ công trước.

## 20. Kết luận

Retry một thao tác có tác động bên ngoài mà thiếu tính lũy đẳng có thể nhân đôi thanh toán, email, shipment, quyền truy cập hoặc message. Timeout không chứng minh request chưa được thực hiện; rollback database cũng không thể hoàn tác tác dụng đã xảy ra ở hệ thống khác.

Tạo idempotency key ổn định cho từng ý định nghiệp vụ và dùng lại key đó qua mọi retry. Lưu key, request hash, trạng thái và kết quả bền vững; dùng unique constraint để phân xử request trùng; từ chối cùng key với payload khác. Transactional outbox giúp lưu ý định gọi bên ngoài cùng thay đổi database, còn inbox giúp consumer deduplicate message đầu vào. Tuy vậy, outbox/inbox không tự tạo exactly-once end-to-end: provider cần hỗ trợ idempotency hoặc tra cứu, và operation có kết quả chưa xác định cần reconciliation. Hãy retry có giới hạn, phân loại lỗi, giữ trạng thái operation rõ ràng và kiểm thử các cửa sổ crash/timeout để bảo đảm một ý định nghiệp vụ không tạo nhiều tác dụng phụ.
