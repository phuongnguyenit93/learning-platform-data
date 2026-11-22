# Khóa nghiệp vụ, tính lũy đẳng (idempotency) và chống xử lý sự kiện trùng

Trong hệ thống có nhiều request, worker và dịch vụ cùng ghi vào MySQL, một thao tác nghiệp vụ có thể được gửi lại nhiều lần. Người dùng bấm nút thanh toán hai lần, client retry vì timeout, message broker giao lại event sau khi consumer mất kết nối, hoặc hai worker cùng xử lý một đơn hàng. Nếu mỗi lần nhận đều tạo tác động mới, hệ thống có thể tạo đơn trùng, trừ tiền hai lần hoặc gửi thông báo lặp.

Để xử lý an toàn, cần kết hợp ba lớp: khóa nghiệp vụ duy nhất ở database, tính lũy đẳng của request/consumer và transaction bảo đảm dấu vết xử lý đi cùng thay đổi dữ liệu. Khóa dòng giúp tuần tự hóa các cập nhật cạnh tranh; unique constraint là trọng tài cuối cùng cho những thao tác phải duy nhất. Với tích hợp qua message broker, inbox/outbox giúp xử lý giao nhận lặp mà không giả định mạng có thể bảo đảm exactly-once end-to-end.

Bài học sử dụng MySQL 8.4, InnoDB và Java/Spring ở mức ví dụ. Các mẫu thiết kế cũng áp dụng cho dịch vụ khác kết nối MySQL qua JDBC.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt khóa nghiệp vụ, khóa kỹ thuật, khóa dòng và idempotency key.
- Dùng unique constraint để chặn hai request tạo cùng một tác động nghiệp vụ.
- Thiết kế bảng lưu idempotency key và fingerprint của request.
- Xử lý request lặp bằng cách trả lại kết quả đã lưu.
- Dùng inbox pattern để chống xử lý event trùng trong cùng transaction với business update.
- Dùng transactional outbox để ghi thay đổi nghiệp vụ và event một cách nguyên tử.
- Chọn pessimistic lock, optimistic lock hoặc compare-and-set theo loại cạnh tranh.
- Xử lý deadlock, lock timeout, retry và thời hạn lưu dấu vết idempotency.
- Hiểu giới hạn của tuyên bố exactly-once trong hệ thống phân tán.

## 1. Những loại khóa và vấn đề cần giải quyết

Các khái niệm sau có liên quan nhưng không thay thế nhau:

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Khóa nghiệp vụ (business key) | Định danh một thực thể hoặc thao tác theo quy tắc nghiệp vụ | Mã đơn hàng từ đối tác, mã giao dịch thanh toán |
| Khóa chính (primary key) | Định danh duy nhất một hàng trong database | `orders.id` |
| Unique constraint | Bảo đảm một giá trị hoặc tổ hợp giá trị không xuất hiện hai lần | `UNIQUE(provider, provider_transaction_id)` |
| Khóa dòng (row lock) | Tuần tự hóa thao tác đồng thời trên hàng đang tồn tại | `SELECT ... FOR UPDATE` |
| Optimistic version | Phát hiện một transaction cập nhật trên dữ liệu đã bị thay đổi | Cột `version` hoặc JPA `@Version` |
| Idempotency key | Nhận diện các lần gửi lại của cùng một yêu cầu logic | Header `Idempotency-Key` |
| Event ID / inbox key | Nhận diện một event đã được consumer xử lý | `(consumer_name, event_id)` |

Khóa dòng không thay thế unique constraint. Hai transaction có thể cùng kiểm tra một khóa chưa tồn tại rồi cùng cố gắng insert; unique constraint mới là cơ chế quyết định một transaction thắng. Ngược lại, unique constraint không tự bảo đảm toàn bộ quy trình nhiều bước được thực hiện đúng thứ tự nghiệp vụ; transaction và khóa dòng vẫn có vai trò riêng.

## 2. Bắt đầu từ khóa nghiệp vụ duy nhất

Giả sử đối tác gửi đơn hàng với mã tham chiếu riêng. Một đơn hàng của cùng đối tác không được tạo hai lần:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    merchant_id BIGINT UNSIGNED NOT NULL,
    external_order_no VARCHAR(100)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_orders_merchant_external (
        merchant_id, external_order_no
    )
) ENGINE = InnoDB;
```

Unique key `(merchant_id, external_order_no)` thể hiện quy tắc nghiệp vụ: cùng một merchant không thể có hai đơn hàng với cùng mã từ hệ thống đối tác. Nếu cùng mã có thể hợp lệ ở hai merchant khác nhau, `merchant_id` phải nằm trong unique key.

Không chỉ kiểm tra bằng một câu SELECT trước khi INSERT:

```sql
SELECT id
FROM orders
WHERE merchant_id = 42
  AND external_order_no = 'EXT-2026-001';

-- Sau đó mới INSERT nếu không thấy hàng.
```

Hai request đồng thời có thể đều không thấy hàng, rồi cùng insert. Đây là race condition kiểu check-then-act. Giải pháp là đặt unique constraint và để InnoDB phân xử nguyên tử:

```sql
INSERT INTO orders (
    merchant_id, external_order_no, status,
    total_amount, created_at
)
VALUES (42, 'EXT-2026-001', 'PENDING', 125000.00, NOW(6));
```

Một request insert thành công; request còn lại nhận duplicate-key error. Ứng dụng cần đọc hàng đã có, so sánh dữ liệu nghiệp vụ và trả kết quả phù hợp. Nếu cùng business key nhưng payload khác nhau, không được âm thầm ghi đè đơn hàng cũ.

### 2.1. Chọn phạm vi của business key

Trước khi tạo unique key, trả lời:

- Đơn vị nào sở hữu tính duy nhất: toàn hệ thống, tenant, merchant hay từng loại thao tác?
- Khóa có phân biệt chữ hoa/chữ thường không?
- Có khoảng trắng hoặc Unicode normalization cần chuẩn hóa không?
- Khóa có thể được tái sử dụng sau khi hủy hoặc xóa không?
- Dữ liệu lịch sử có phải được giữ lại vĩnh viễn không?

Với mã do hệ thống ngoài cấp, cần xác định quy tắc so sánh rõ ràng. Collation không phân biệt hoa/thường có thể coi `abc-01` và `ABC-01` là cùng khóa. Nếu đối tác quy định mã phân biệt byte, dùng kiểu/collation nhị phân hoặc chuẩn hóa trước khi lưu.

### 2.2. Duplicate key là kết quả nghiệp vụ cần xử lý

Không phải mọi duplicate-key error đều là lỗi hệ thống. Nó có thể có nghĩa request đã được xử lý trước đó. Hãy phân biệt constraint nào vi phạm:

- Trùng business key của đơn hàng: tìm đơn hàng đã tồn tại và xác minh payload.
- Trùng ID giao dịch từ cổng thanh toán: không ghi nhận thanh toán lần hai.
- Trùng event inbox key: consumer đã xử lý event đó.
- Trùng một unique key không liên quan: có thể là lỗi dữ liệu thực sự, cần báo lỗi.

Không bắt mọi `DuplicateKeyException` rồi trả HTTP 200. Chỉ coi là duplicate đã xử lý khi tìm được đúng khóa duy nhất của thao tác và xác minh nội dung tương ứng.

## 3. Idempotency cho HTTP/API request

### 3.1. Idempotency có nghĩa gì?

Một thao tác là idempotent nếu thực hiện lại cùng yêu cầu logic không làm phát sinh thêm tác động nghiệp vụ. Ví dụ, gửi lại yêu cầu tạo một thanh toán với cùng idempotency key phải trả lại kết quả thanh toán đã tạo, không tạo một khoản thanh toán thứ hai.

Idempotency key thường được client gửi trong header:

```http
POST /payments
Idempotency-Key: 2d1f8d9e-8c6a-4b8d-a6f7-4c1a1a2b3c4d
Content-Type: application/json

{
  "orderId": 8123,
  "amount": 125000
}
```

Server phải định nghĩa key có phạm vi theo tenant, endpoint/operation và khoảng thời gian lưu. Một key ngẫu nhiên không tự làm request idempotent; server cần lưu key và kết quả trong database.

### 3.2. Bảng lưu idempotency key

Ví dụ schema:

```sql
CREATE TABLE api_idempotency (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    operation VARCHAR(80)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    idempotency_key VARBINARY(128) NOT NULL,
    owner_token BINARY(16) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    state ENUM('PROCESSING', 'SUCCEEDED') NOT NULL,
    response_code SMALLINT UNSIGNED NULL,
    response_body JSON NULL,
    resource_id BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_idempotency_scope (
        tenant_id, operation, idempotency_key
    ),
    KEY idx_idempotency_created (created_at)
) ENGINE = InnoDB;
```

Ý nghĩa các cột:

- `tenant_id` và `operation` giới hạn phạm vi của key. Hai API khác nhau có thể dùng cùng chuỗi key mà không xung đột.
- `idempotency_key` dùng `VARBINARY` để so sánh chính xác byte, tránh collation vô tình gộp hai key khác nhau.
- `request_hash` là SHA-256 của request đã chuẩn hóa, dùng phát hiện cùng key nhưng payload khác.
- `owner_token` là 16 byte ngẫu nhiên do request hiện tại tạo. Nó giúp phân biệt transaction vừa tạo bản ghi với request đang gặp bản ghi đã tồn tại.
- `state` và các trường response lưu kết quả để phát lại cho client.

Không lưu password, token bí mật hoặc thông tin thẻ thanh toán trong idempotency record. Chỉ lưu phần response cần thiết và áp dụng chính sách bảo vệ dữ liệu phù hợp.

### 3.3. Cùng key nhưng payload khác phải bị từ chối

Client có thể gửi lại key cũ do bug nhưng thay đổi `amount` hoặc `orderId`. Nếu server chỉ kiểm tra key, nó có thể trả nhầm kết quả của request trước cho một yêu cầu khác.

Tạo fingerprint ổn định từ các trường có ý nghĩa nghiệp vụ:

```text
request_hash = SHA-256(
    canonical(operation, tenant_id, order_id, amount, currency)
)
```

Canonicalization phải ổn định: cùng dữ liệu logic cho cùng hash dù thứ tự field JSON hoặc khoảng trắng khác nhau. Không hash trực tiếp chuỗi JSON tùy ý nếu serializer có thể thay đổi thứ tự hoặc định dạng. Bao gồm những trường ảnh hưởng đến tác động nghiệp vụ; loại bỏ metadata không liên quan như request timestamp.

Nếu key đã tồn tại:

- Hash giống nhau và đã thành công: phát lại kết quả đã lưu.
- Hash khác nhau: trả lỗi conflict, ví dụ HTTP 409.
- Đang xử lý trong một workflow nhiều giai đoạn: trả trạng thái đang xử lý hoặc cho client retry sau; không khởi chạy tác động thứ hai.

### 3.4. Thực hiện claim và business update trong cùng transaction

Đối với thao tác hoàn toàn nằm trong một MySQL database, có thể insert idempotency record, cập nhật nghiệp vụ và lưu response trong cùng một transaction.

Ví dụ phần claim:

```sql
INSERT INTO api_idempotency (
    tenant_id, operation, idempotency_key,
    owner_token, request_hash, state, created_at
)
VALUES (
    ?, ?, ?, ?, ?, 'PROCESSING', NOW(6)
)
ON DUPLICATE KEY UPDATE id = id;

SELECT id, owner_token, request_hash, state,
       response_code, response_body, resource_id
FROM api_idempotency
WHERE tenant_id = ?
  AND operation = ?
  AND idempotency_key = ?
FOR UPDATE;
```

Ứng dụng tạo `owner_token` mới cho mỗi lần thử. Sau câu upsert, đọc hàng bằng `FOR UPDATE`:

1. Nếu `owner_token` trong hàng bằng token của request hiện tại, transaction này vừa tạo key và được phép thực hiện nghiệp vụ.
2. Nếu token khác, key đã được một request khác tạo trước đó. So sánh `request_hash`.
3. Nếu hash khác, trả conflict.
4. Nếu state là `SUCCEEDED`, trả lại response đã lưu.
5. Nếu state là `PROCESSING` đã commit từ một workflow nhiều giai đoạn, trả trạng thái đang xử lý theo hợp đồng API.

Trong mô hình một transaction, hàng `PROCESSING` mới được insert vẫn chưa commit nên request khác không đọc thấy trạng thái dở dang. Upsert trùng phải chờ transaction đầu giải phóng unique-key lock. Nếu transaction đầu commit, request sau đọc được kết quả `SUCCEEDED`; nếu transaction đầu rollback, request sau có thể insert key và thực hiện nghiệp vụ.

Phần xử lý tiếp tục trong cùng transaction:

```sql
-- Chỉ chạy khi owner_token khớp với request hiện tại.
INSERT INTO payments (
    tenant_id, order_id, amount, status, created_at
)
VALUES (?, ?, ?, 'SUCCEEDED', NOW(6));

SET @payment_id = LAST_INSERT_ID();

UPDATE api_idempotency
SET state = 'SUCCEEDED',
    response_code = 201,
    response_body = ?,
    resource_id = @payment_id,
    completed_at = NOW(6)
WHERE id = ?;

COMMIT;
```

Ví dụ giả định payment insert và cập nhật idempotency dùng cùng connection. Trong ứng dụng thực tế, lấy generated ID rõ ràng từ JDBC/JPA rồi bind vào `resource_id`; không phụ thuộc ngầm vào trạng thái `LAST_INSERT_ID()` nếu giữa hai câu lệnh có thêm INSERT khác.

Điểm quan trọng là business row và kết quả idempotency commit cùng nhau. Nếu bất kỳ bước nào thất bại, rollback sẽ xóa cả idempotency claim lẫn thay đổi nghiệp vụ. Request retry sau đó có thể thử lại an toàn.

`ON DUPLICATE KEY UPDATE id = id` là thao tác no-op để đợi/khóa hàng có cùng unique key; bảng này nên chỉ có unique key nghiệp vụ idempotency đã dự kiến (ngoài primary key). Tránh thêm trigger tạo tác động phụ vào bảng idempotency. Kiểm tra đúng constraint bị conflict và kiểm thử hành vi concurrency trên phiên bản MySQL đang chạy.

### 3.5. Ranh giới transaction khi gọi dịch vụ ngoài

Không giữ transaction MySQL mở trong lúc gọi cổng thanh toán, email provider hoặc API bên ngoài. Database không thể rollback một khoản tiền đã bị hệ thống khác trừ, và network timeout không cho biết chắc request ngoài đã thành công hay chưa.

Với tác động bên ngoài:

1. Ghi yêu cầu nghiệp vụ và outbox event trong một transaction MySQL.
2. Commit.
3. Worker gửi lệnh đến dịch vụ ngoài bằng một idempotency key ổn định.
4. Ghi nhận kết quả callback/response trong transaction khác.
5. Retry theo cùng key; xử lý timeout bằng cách tra cứu trạng thái từ provider nếu API hỗ trợ.

Đây là workflow nhiều giai đoạn. Bản ghi `PROCESSING` có thể được commit để thể hiện công việc đang chờ, nhưng phải có lease, timeout, retry policy và trạng thái cuối. Không để một bản ghi processing tồn tại vô hạn mà không có cơ chế phục hồi.

## 4. Khóa nghiệp vụ cho thanh toán và chuyển trạng thái

Idempotency key ở API ngăn cùng request được áp dụng nhiều lần. Unique business key ở bảng thanh toán bảo vệ thêm khi có client khác, worker khác hoặc luồng tích hợp không dùng chung idempotency key.

Ví dụ mỗi giao dịch provider chỉ được ghi nhận một lần:

```sql
CREATE TABLE payment_transactions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    provider VARCHAR(40)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    provider_transaction_id VARCHAR(150)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(14,2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_provider_transaction (
        provider, provider_transaction_id
    ),
    KEY idx_payment_order (order_id)
) ENGINE = InnoDB;
```

Khi webhook provider gửi lại cùng `provider_transaction_id`, unique key chặn hàng thanh toán thứ hai. Consumer đọc bản ghi hiện có và xác minh order, amount, currency và trạng thái. Nếu cùng provider transaction ID nhưng amount khác, đó là xung đột cần điều tra hoặc đưa vào quarantine, không được coi là duplicate hợp lệ.

### 4.1. Chuyển trạng thái có điều kiện

Một số nghiệp vụ có thể dùng compare-and-set:

```sql
UPDATE orders
SET status = 'CONFIRMED',
    updated_at = NOW(6)
WHERE id = ?
  AND status = 'PENDING';
```

Nếu số hàng bị ảnh hưởng bằng 1, request đã chuyển trạng thái. Nếu bằng 0, đơn hàng không còn ở trạng thái `PENDING`, không tồn tại hoặc không thỏa điều kiện. Đọc trạng thái hiện tại để phân biệt. Cách này giúp tránh hai request cùng chuyển một đơn hàng qua cùng một transition.

Đối với thao tác trừ tiền hoặc cập nhật tồn kho, phải kiểm tra điều kiện ngay trong câu UPDATE:

```sql
UPDATE inventory
SET available_quantity = available_quantity - ?,
    updated_at = NOW(6)
WHERE product_id = ?
  AND available_quantity >= ?;
```

Nếu `ROW_COUNT()` là 0, không đủ hàng hoặc product không tồn tại. Tránh đọc số lượng trước rồi cập nhật sau mà không khóa hoặc kiểm tra lại trong câu lệnh ghi.

### 4.2. Không dùng idempotency thay thế kiểm tra nghiệp vụ

Hai request có idempotency key khác nhau vẫn có thể cố mua cùng một sản phẩm hoặc thanh toán cùng một hóa đơn. Vì vậy:

- Idempotency key nhận diện lần gửi lại của một request logic.
- Unique business key bảo đảm thực thể/thao tác nghiệp vụ không bị tạo trùng.
- Điều kiện trạng thái và transaction bảo vệ các transition hợp lệ.
- Row lock hoặc optimistic version xử lý cạnh tranh khi nhiều request cập nhật cùng tài nguyên.

Các lớp này bổ sung cho nhau.

## 5. Khóa dòng trong InnoDB

### 5.1. Pessimistic locking với SELECT ... FOR UPDATE

Khi cần đọc một hàng rồi tính toán và cập nhật dựa trên giá trị hiện tại, có thể khóa hàng trong transaction:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 100
FOR UPDATE;

-- Ứng dụng kiểm tra số dư và tính số tiền hợp lệ.
UPDATE accounts
SET balance = balance - 50000
WHERE account_id = 100;

COMMIT;
```

`FOR UPDATE` là locking read. Với InnoDB, transaction giữ khóa cho đến commit hoặc rollback. Transaction khác muốn cập nhật/khóa cùng hàng sẽ phải chờ hoặc nhận lỗi theo timeout/locking option.

Điều kiện tìm kiếm nên dùng index phù hợp. Nếu truy vấn khóa theo một cột không có index hoặc phạm vi rộng, InnoDB có thể khóa nhiều record/range hơn mong đợi, làm giảm concurrency. Hãy dùng khóa chính hoặc unique key khi chỉ cần bảo vệ một hàng.

### 5.2. NOWAIT và SKIP LOCKED

MySQL 8.0 hỗ trợ locking read với `NOWAIT` và `SKIP LOCKED`:

- `NOWAIT`: nếu hàng cần khóa đang bị transaction khác khóa, câu lệnh trả lỗi ngay.
- `SKIP LOCKED`: bỏ qua các hàng đang bị khóa và trả các hàng có thể lấy ngay.

Ví dụ worker lấy job từ hàng đợi:

```sql
START TRANSACTION;

SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY priority DESC, id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- Cập nhật các ID vừa lấy thành RUNNING và gán worker.
COMMIT;
```

`SKIP LOCKED` phù hợp cho queue worker vì nhiều worker có thể lấy các hàng khác nhau mà không phải chờ nhau. Kết quả là một view không nhất quán của hàng đợi; không dùng nó cho truy vấn nghiệp vụ cần thấy toàn bộ dữ liệu. Sau khi claim, lưu owner/lease và có cơ chế thu hồi job nếu worker chết.

### 5.3. Không giữ khóa trong khi làm việc chậm

Transaction có khóa nên chỉ bao gồm các thao tác database cần thiết. Không gọi HTTP, gửi email, ghi file hoặc chờ người dùng trong khi đang giữ row lock. Transaction dài làm tăng thời gian chờ, nguy cơ deadlock, undo history và giảm throughput.

### 5.4. Named lock không phải khóa giao dịch dữ liệu

MySQL có `GET_LOCK()` để lấy named lock theo session. Named lock có thể hữu ích cho một số tác vụ điều phối, nhưng:

- Không thay thế unique constraint hoặc row lock.
- Không tự rollback theo transaction.
- Gắn với session/connection; pool có thể tái sử dụng connection.
- Cần giải phóng đúng cách và xử lý mất kết nối.
- Không tạo được khóa phân tán đáng tin cậy giữa các hệ thống database độc lập nếu thiết kế không xét failover.

Không dùng named lock làm lớp bảo vệ duy nhất cho thanh toán, tồn kho hoặc chống event trùng. Dữ liệu vẫn phải có unique constraint và transaction.

## 6. Optimistic locking với version

Nếu xung đột ít và không muốn khóa hàng trong thời gian đọc/tính toán, dùng optimistic locking. Mỗi hàng có cột `version`:

```sql
ALTER TABLE inventory
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

Khi đọc, ứng dụng lấy cả `available_quantity` và `version`. Khi cập nhật:

```sql
UPDATE inventory
SET available_quantity = ?,
    version = version + 1,
    updated_at = NOW(6)
WHERE product_id = ?
  AND version = ?;
```

Nếu affected rows bằng 1, update thành công. Nếu bằng 0, dữ liệu đã bị transaction khác thay đổi hoặc hàng không còn tồn tại; ứng dụng đọc lại và quyết định thử lại hay trả conflict.

Trong JPA:

```java
@Entity
public class Inventory {
    @Id
    private Long productId;

    private Integer availableQuantity;

    @Version
    private Long version;
}
```

Hibernate thêm điều kiện version vào câu UPDATE và tăng version khi flush. Nếu version không còn khớp, ứng dụng nhận optimistic locking exception. Bắt lỗi ở ranh giới transaction, rollback transaction cũ rồi mới đọc lại/thử lại trong transaction mới.

Chọn cách khóa:

| Tình huống | Gợi ý |
|---|---|
| Một tài khoản/đơn hàng ít được cập nhật đồng thời, muốn phát hiện xung đột | Optimistic version |
| Cần đọc trạng thái rồi cập nhật trong một transaction ngắn, xung đột cao | `SELECT ... FOR UPDATE` |
| Chỉ cần chuyển trạng thái nếu đang ở trạng thái mong đợi | Conditional `UPDATE ... WHERE status = ...` |
| Bảo đảm một business key chỉ tồn tại một lần | Unique constraint |
| Nhiều worker chia nhau hàng queue | `FOR UPDATE SKIP LOCKED` kết hợp lease |

## 7. Inbox pattern: chống xử lý event trùng

Message broker thường cung cấp giao nhận ít nhất một lần (at-least-once). Consumer có thể xử lý event thành công rồi chết trước khi ACK; broker sẽ giao lại. Đây là hành vi bình thường, vì broker không thể biết chắc transaction database của consumer đã commit hay chưa.

Inbox pattern lưu ID event đã xử lý trong cùng database và transaction với business update.

### 7.1. Bảng inbox

```sql
CREATE TABLE event_inbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    consumer_name VARCHAR(100)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    producer_name VARCHAR(100)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    event_id VARBINARY(128) NOT NULL,
    payload_hash BINARY(32) NOT NULL,
    received_at DATETIME(6) NOT NULL,
    processed_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_inbox_consumer_event (
        consumer_name, producer_name, event_id
    )
) ENGINE = InnoDB;
```

Unique key theo consumer và producer giúp cùng một event có thể được xử lý bởi nhiều consumer logic khác nhau nhưng mỗi consumer chỉ áp dụng event một lần. Nếu event ID chỉ duy nhất trong một topic hoặc partition, đưa thêm định danh stream/topic vào khóa.

### 7.2. Thứ tự xử lý đúng

Consumer thực hiện trong một transaction:

1. Insert event ID vào inbox.
2. Nếu insert mới thành công, áp dụng thay đổi nghiệp vụ.
3. Cập nhật `processed_at`.
4. Commit transaction.
5. Sau khi commit thành công, ACK message cho broker.

Nếu business update thất bại, rollback sẽ xóa luôn inbox row chưa commit; broker giao lại thì consumer có thể thử lại. Nếu commit thành công nhưng ACK bị mất, lần giao lại gặp unique key đã tồn tại và consumer bỏ qua tác động nghiệp vụ, sau đó ACK.

Không ACK trước khi transaction commit. Nếu ACK trước rồi transaction rollback hoặc database gặp sự cố, event có thể bị mất khỏi luồng xử lý.

### 7.3. Mẫu Java với transaction boundary rõ ràng

Ví dụ dùng `TransactionTemplate` để việc kiểm tra duplicate diễn ra sau khi transaction thất bại đã rollback:

```java
public void onMessage(OrderPaidEvent event) {
    byte[] payloadHash = hashCanonicalPayload(event);

    try {
        transactionTemplate.executeWithoutResult(tx -> {
            inboxRepository.insert(
                "order-projection",
                event.producer(),
                event.eventId(),
                payloadHash
            );

            orderProjection.apply(event);

            inboxRepository.markProcessed(
                "order-projection",
                event.producer(),
                event.eventId()
            );
        });

        broker.ack(event);
    } catch (DuplicateKeyException ex) {
        // TransactionTemplate đã rollback trước khi trả exception.
        var existing = inboxRepository.find(
            "order-projection",
            event.producer(),
            event.eventId()
        );

        if (existing.isPresent()
                && MessageDigest.isEqual(
                    existing.get().payloadHash(),
                    payloadHash)) {
            broker.ack(event);
            return;
        }

        if (existing.isPresent()) {
            quarantine(event, "Same event ID with different payload");
            broker.ack(event);
            return;
        }

        // Duplicate key phát sinh từ một constraint khác trong business update.
        throw ex;
    }
}
```

Đây là khung minh họa. `inboxRepository.insert`, `orderProjection.apply` và `markProcessed` phải dùng cùng DataSource/transaction manager để cùng một transaction. `find` sau rollback phải chạy trong transaction mới hoặc read operation độc lập. Nếu duplicate key phát sinh từ constraint nghiệp vụ khác, không được nhầm thành event đã xử lý; vì inbox insert đã rollback nên truy vấn inbox sẽ không tìm thấy event.

Nếu cùng event ID nhưng payload hash khác, producer có thể đã tái sử dụng ID sai hoặc dữ liệu bị biến đổi. Đưa vào quarantine/dead-letter và cảnh báo vận hành; không âm thầm ACK như duplicate hợp lệ nếu hợp đồng hệ thống yêu cầu điều tra.

### 7.4. Inbox không thể bao trùm external side effect

Nếu consumer cập nhật MySQL rồi gọi API gửi email trong cùng phương thức, transaction database không thể rollback email đã gửi. Nếu consumer gửi email trước rồi transaction rollback, event redelivery có thể gửi email lần nữa.

Với external side effect, ghi một outbox command cùng transaction với inbox/business update. Một worker riêng gửi email hoặc gọi API; phía nhận cũng nên hỗ trợ idempotency key. Nếu không có hỗ trợ, cần thiết kế retry/reconciliation và chấp nhận khả năng duplicate theo đặc tính hệ thống ngoài.

## 8. Transactional outbox: không mất event sau commit

Một lỗi phổ biến là:

1. Commit thay đổi đơn hàng vào MySQL.
2. Publish event lên broker.

Nếu ứng dụng chết giữa hai bước, database đã đổi nhưng event không được gửi. Đảo thứ tự cũng có rủi ro: publish thành công nhưng transaction database rollback, consumer nhận một event không có trạng thái tương ứng.

Transactional outbox giải quyết bằng cách ghi business data và event vào cùng một transaction MySQL.

### 8.1. Bảng outbox

```sql
CREATE TABLE event_outbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_id BINARY(16) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    claimed_by VARCHAR(100) NULL,
    lease_until DATETIME(6) NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_outbox_event (event_id),
    KEY idx_outbox_pending (published_at, lease_until, id)
) ENGINE = InnoDB;
```

### 8.2. Ghi business state và event cùng transaction

```sql
START TRANSACTION;

UPDATE orders
SET status = 'CONFIRMED',
    updated_at = NOW(6)
WHERE id = 8123
  AND status = 'PENDING';

-- Chỉ ghi event nếu transition thực sự thành công.
INSERT INTO event_outbox (
    event_id, aggregate_type, aggregate_id,
    event_type, payload, created_at
)
VALUES (
    UUID_TO_BIN(UUID()), 'ORDER', 8123,
    'OrderConfirmed',
    JSON_OBJECT('orderId', 8123, 'status', 'CONFIRMED'),
    NOW(6)
);

COMMIT;
```

Trong ứng dụng, kiểm tra affected rows của UPDATE trước khi tạo event. Nếu không có transition, không tạo event xác nhận mới. Nếu cần bảo đảm thứ tự event theo aggregate, thêm aggregate version/sequence và để publisher phát theo thứ tự đã thiết kế.

### 8.3. Publisher claim bằng lease

Không giữ transaction và row lock trong lúc chờ broker qua mạng. Một worker có thể claim một nhóm event bằng transaction ngắn:

```sql
START TRANSACTION;

SELECT id
FROM event_outbox
WHERE published_at IS NULL
  AND (lease_until IS NULL OR lease_until < NOW(6))
ORDER BY id
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- Với các ID vừa chọn, cập nhật:
-- claimed_by = worker ID
-- lease_until = NOW(6) + INTERVAL 30 SECOND
-- attempts = attempts + 1

COMMIT;
```

Sau commit, worker đọc payload và publish. Khi broker xác nhận nhận message, worker cập nhật `published_at` và xóa lease. Nếu worker chết trước khi publish, lease hết hạn và worker khác claim lại.

Có một cửa sổ không thể loại bỏ hoàn toàn: broker đã nhận event nhưng worker chết trước khi cập nhật `published_at`. Event sẽ được publish lại sau khi lease hết hạn. Vì vậy, outbox thường bảo đảm không mất event nhưng vẫn có thể phát trùng; consumer inbox phải idempotent.

`SKIP LOCKED` giúp nhiều publisher lấy các hàng khác nhau. Lease cần dài hơn thời gian publish thông thường và có cơ chế gia hạn nếu xử lý lâu. Không để một worker giữ claim vĩnh viễn.

## 9. Exactly-once và giới hạn của hệ thống phân tán

Không nên hứa rằng toàn bộ chuỗi HTTP → MySQL → broker → consumer → API ngoài chỉ chạy đúng một lần. Timeout, process crash, network partition và ACK bị mất khiến bên gửi không thể luôn biết bên nhận đã hoàn thành hay chưa.

Thiết kế thực tế thường gồm:

- Giao nhận at-least-once: message có thể được giao lại.
- Idempotency ở API và consumer: cùng key/event không lặp business effect.
- Unique business constraints: chặn thực thể hoặc giao dịch trùng.
- Transactional inbox/outbox: gắn dấu vết xử lý với thay đổi database.
- Reconciliation: đối chiếu trạng thái với provider hoặc hệ thống ngoài khi kết quả không rõ.

Có thể đạt “một tác động nghiệp vụ hiệu lực” trong phạm vi một database transaction nếu dấu vết idempotency và business update commit/rollback cùng nhau. Với nhiều hệ thống độc lập, cần saga, outbox/inbox và idempotency ở từng bước; không có một transaction MySQL nào bao trùm tất cả.

## 10. Deadlock, lock timeout và retry an toàn

Khi nhiều transaction khóa các hàng theo thứ tự khác nhau, InnoDB có thể phát hiện deadlock và rollback một transaction làm nạn nhân. Các lỗi thường gặp:

- `1213` / SQLSTATE `40001`: deadlock found.
- `1205`: lock wait timeout exceeded.

Ví dụ hai transaction:

```text
Transaction A             Transaction B
-------------             -------------
lock account 1            lock account 2
wait account 2            wait account 1
```

Giảm deadlock bằng cách:

1. Khóa các hàng theo cùng thứ tự toàn hệ thống, ví dụ tăng dần theo primary key.
2. Giữ transaction ngắn, chỉ khóa hàng cần thiết.
3. Dùng index để truy vấn khóa hẹp.
4. Không gọi dịch vụ ngoài khi đang giữ lock.
5. Thiết kế batch nhỏ, tránh cập nhật phạm vi lớn không cần thiết.

Khi deadlock hoặc lock timeout xảy ra, retry toàn bộ transaction từ đầu với số lần giới hạn, backoff và jitter. Không chỉ retry câu UPDATE cuối vì những quyết định đọc trước đó có thể không còn hợp lệ. Mọi tác động bên ngoài phải dùng idempotency key hoặc outbox để retry không tạo tác động trùng.

Timeout khi COMMIT hoặc mất kết nối ngay sau commit tạo trạng thái không rõ: transaction có thể đã commit dù client không nhận được response. Trước khi chạy lại thao tác, tra cứu idempotency/business key để xác định kết quả đã lưu.

## 11. Retention và vận hành idempotency

### 11.1. Lưu key đủ lâu

Thời hạn lưu idempotency key phải dài hơn khoảng thời gian client, gateway, broker hoặc đối tác có thể retry. Nếu xóa key quá sớm, một request cũ được gửi lại có thể tạo tác động lần nữa.

Đối với thao tác tài chính, khóa provider transaction hoặc business reference có thể cần lưu lâu hơn nhiều so với idempotency key HTTP. Giữ unique business constraint trên dữ liệu giao dịch để có lớp bảo vệ bền vững.

### 11.2. Dọn dữ liệu theo batch

Nếu bảng idempotency có thời hạn, xóa theo batch nhỏ và có index trên thời điểm hết hạn:

```sql
DELETE FROM api_idempotency
WHERE created_at < NOW(6) - INTERVAL 30 DAY
ORDER BY created_at
LIMIT 1000;
```

Chỉ xóa sau khi hết retry window và không còn workflow đang xử lý. Với event inbox, giữ record lâu hơn broker retention và khoảng thời gian replay có thể xảy ra. Nếu cần replay có chủ đích, dùng consumer/version namespace mới hoặc quy trình reset có kiểm soát; không xóa inbox tùy tiện.

### 11.3. Theo dõi chỉ số

Theo dõi ít nhất:

- Số request trùng theo operation/tenant.
- Số lần cùng idempotency key nhưng payload hash khác.
- Số event bị inbox deduplicate và số event vào quarantine.
- Số outbox pending, tuổi của event cũ nhất và số lần publish retry.
- Số deadlock, lock wait timeout và transaction retry.
- Số bản ghi `PROCESSING` quá hạn và lease hết hạn.
- Tỷ lệ duplicate business key ở từng integration.

Log nên chứa operation, tenant/business reference, event ID và trace ID phù hợp. Không ghi toàn bộ payload nhạy cảm hoặc credentials vào log.

## 12. Quy trình xử lý một event thanh toán

Giả sử provider gửi event `PaymentSucceeded` nhiều lần:

1. Xác thực chữ ký webhook và danh tính provider trước khi xử lý.
2. Xác định event ID và provider transaction ID; kiểm tra event ID có ổn định giữa các lần retry không.
3. Bắt đầu transaction MySQL.
4. Insert event ID vào inbox với unique key theo consumer/provider/event.
5. Nếu event đã có và payload hash khớp, kết thúc transaction mà không áp dụng business effect lần nữa; ACK sau khi kiểm tra hoàn tất.
6. Nếu event mới, kiểm tra unique provider transaction ID và xác minh order/amount/currency.
7. Cập nhật payment/order theo transition hợp lệ; dùng điều kiện trạng thái hoặc row lock nếu cần.
8. Ghi outbox event như `OrderPaid` trong cùng transaction.
9. Commit transaction rồi ACK webhook/message.
10. Publisher gửi outbox event; downstream consumer dùng inbox riêng để deduplicate.

Nếu provider transaction ID đã tồn tại nhưng tham chiếu order hoặc amount không khớp, đưa sự kiện vào quy trình điều tra. Không bỏ qua chỉ vì event ID hoặc provider transaction ID đã xuất hiện.

## 13. Kiểm thử concurrency và failure

Một bài test tuần tự không chứng minh idempotency hoạt động dưới concurrency. Kiểm thử bằng nhiều connection/worker đồng thời:

1. Gửi 20 request song song với cùng tenant, operation, key và payload. Kỳ vọng chỉ có một business row; tất cả response tương đương.
2. Gửi cùng key nhưng amount khác. Kỳ vọng một request thành công và request khác nhận conflict.
3. Gửi hai key khác nhau nhưng cùng business key. Kỳ vọng unique business constraint chỉ cho một thao tác tạo tài nguyên.
4. Gửi cùng event nhiều lần song song. Kỳ vọng một inbox row và một business effect.
5. Làm consumer chết sau commit nhưng trước ACK. Khi broker giao lại, consumer phải bỏ qua effect và ACK.
6. Làm consumer chết trước commit. Transaction rollback cả inbox và business update; lần giao lại được phép xử lý.
7. Làm publisher chết sau khi broker nhận event nhưng trước khi đánh dấu published. Event có thể được gửi lại; consumer phải deduplicate.
8. Tạo deadlock có kiểm soát và xác nhận retry toàn transaction không nhân đôi tác động.
9. Mô phỏng timeout sau commit và xác nhận retry trả lại kết quả cũ.

Kiểm tra cả số lượng hàng, trạng thái cuối, tổng tiền/tồn kho và số event phát ra. Không chỉ kiểm tra HTTP status code.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Người dùng retry tạo hai đơn | Không có idempotency key hoặc unique business key | Thêm key có scope và unique constraint nghiệp vụ |
| Cùng key nhưng payload khác vẫn được chấp nhận | Không lưu/so sánh request hash | Tính fingerprint ổn định và trả conflict |
| Hai worker cùng xử lý một event | Chỉ kiểm tra SELECT trước INSERT | Dùng unique inbox key và transaction |
| Inbox ghi rồi business update lỗi nhưng event bị bỏ | Inbox commit riêng trước business update | Commit inbox và business effect cùng transaction |
| Business update xong nhưng event không được publish | Publish nằm ngoài transaction mà không có outbox | Ghi outbox cùng transaction với business state |
| Event publish lặp sau worker crash | Broker nhận event nhưng publisher chưa đánh dấu published | Dùng inbox idempotent ở consumer |
| DuplicateKeyException bị coi là duplicate hợp lệ | Không kiểm tra constraint và business reference | Xác minh đúng inbox/business key và payload |
| Bản ghi PROCESSING bị treo | Workflow nhiều giai đoạn thiếu lease/recovery | Thêm lease, timeout, retry và trạng thái cuối |
| Deadlock tăng khi tải cao | Khóa theo thứ tự khác nhau hoặc transaction dài | Chuẩn hóa thứ tự lock, rút ngắn transaction, retry có giới hạn |
| Request timeout nhưng không biết đã commit chưa | Mất response sau commit | Tra cứu idempotency key/business key trước khi chạy lại |

## 15. Checklist thiết kế

- [ ] Mỗi thao tác có business key và phạm vi duy nhất được định nghĩa rõ.
- [ ] Unique constraint được tạo trong MySQL; không chỉ kiểm tra tồn tại bằng SELECT.
- [ ] API ghi nhận idempotency key theo tenant/operation.
- [ ] Request hash phát hiện cùng key nhưng payload khác.
- [ ] Business update và idempotency result commit trong cùng transaction khi cùng database.
- [ ] Event inbox có unique key theo consumer và event identity.
- [ ] Inbox insert, business effect và processed marker cùng transaction.
- [ ] Broker ACK chỉ sau commit.
- [ ] Outbox event được ghi cùng transaction với business state.
- [ ] Publisher có lease/recovery; consumer chịu được publish trùng.
- [ ] External API dùng idempotency key riêng hoặc có quy trình reconciliation.
- [ ] Row lock/optimistic version được chọn theo mức độ cạnh tranh.
- [ ] Transaction ngắn, index phù hợp và thứ tự lock nhất quán.
- [ ] Deadlock/timeout retry toàn transaction với giới hạn và backoff.
- [ ] Retention không ngắn hơn retry/replay window.
- [ ] Có metrics cho duplicate, conflict, inbox/outbox lag và retry.
- [ ] Đã kiểm thử đồng thời, crash trước/sau commit và mất ACK.

## 16. Bài tập tự kiểm tra

1. Vì sao một câu SELECT kiểm tra business key trước INSERT không ngăn được hai request đồng thời tạo bản ghi trùng?
2. Idempotency key khác business key ở điểm nào?
3. Vì sao phải so sánh request hash khi client gửi lại cùng idempotency key?
4. Trong mô hình idempotency một transaction, điều gì xảy ra nếu process chết trước commit?
5. Vì sao inbox record và business update phải nằm trong cùng transaction?
6. Vì sao broker ACK phải diễn ra sau khi transaction commit?
7. Outbox có thể publish trùng trong trường hợp nào và consumer xử lý ra sao?
8. Khi nào nên dùng `SELECT ... FOR UPDATE` thay cho optimistic version?
9. Vì sao named lock `GET_LOCK()` không thay thế unique constraint?
10. Khi nhận lỗi deadlock 1213, nên retry câu lệnh cuối hay toàn bộ transaction?
11. Vì sao timeout ngay sau commit cần tra cứu idempotency key trước khi chạy lại?
12. Nếu cùng event ID nhưng payload hash khác, consumer nên làm gì?

**Gợi ý đáp án:** (1) Hai transaction có thể cùng đọc trạng thái chưa tồn tại; unique constraint mới phân xử nguyên tử. (2) Business key định danh thực thể/thao tác theo nghiệp vụ; idempotency key định danh lần gửi lại của một request logic. (3) Để tránh trả nhầm kết quả hoặc bỏ qua một request khác payload. (4) Transaction rollback cả claim và business effect, lần retry có thể xử lý lại. (5) Nếu tách transaction, có thể ghi dấu đã xử lý nhưng business effect thất bại hoặc ngược lại. (6) Nếu ACK trước commit, event có thể mất khi transaction rollback. (7) Publisher chết sau khi broker nhận nhưng trước khi ghi published; consumer deduplicate bằng inbox. (8) Khi cần đọc trạng thái hiện tại rồi cập nhật trong một transaction ngắn và xung đột cao. (9) Named lock gắn session và không bảo vệ tính duy nhất dữ liệu bền vững. (10) Retry toàn bộ transaction với backoff và giới hạn. (11) Vì commit có thể đã thành công dù client không nhận response. (12) Đưa vào quarantine/cảnh báo và điều tra producer hoặc dữ liệu; không coi là duplicate hợp lệ.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: InnoDB Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)
- [MySQL 8.4 Reference Manual: InnoDB Deadlocks](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks.html)
- [MySQL 8.4 Reference Manual: INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
- [MySQL 8.4 Reference Manual: InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual: Locking Functions](https://dev.mysql.com/doc/refman/8.4/en/locking-functions.html)
- [Spring Framework Reference: Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Data JPA Reference: Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
