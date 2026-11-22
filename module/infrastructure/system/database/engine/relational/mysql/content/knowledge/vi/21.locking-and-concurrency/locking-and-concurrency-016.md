# Thiết kế thao tác đồng thời đúng dữ liệu và an toàn khi retry

Một thao tác nghiệp vụ có thể được gửi nhiều lần, chạy đồng thời ở nhiều worker hoặc bị gián đoạn ngay sau khi database đã commit. Nếu chỉ dựa vào thứ tự câu lệnh trong ứng dụng, hệ thống dễ trừ tồn kho hai lần, ghi đè cập nhật mới hơn hoặc tạo hai giao dịch giống nhau. Thiết kế đúng cần bảo vệ các bất biến dữ liệu trong database, xác định ranh giới transaction rõ ràng và làm cho việc thử lại có thể dự đoán.

Với MySQL/InnoDB, có thể kết hợp cập nhật nguyên tử, khóa bi quan, kiểm soát phiên bản lạc quan, ràng buộc duy nhất và idempotency key. Khi xảy ra deadlock hoặc timeout, ứng dụng cần chạy lại toàn bộ đơn vị nghiệp vụ trong transaction mới. Khi kết nối mất trong lúc `COMMIT`, kết quả có thể chưa rõ; một khóa idempotency giúp xác định thao tác đã được xử lý hay chưa.

## Mục tiêu

Sau bài học, bạn có thể:

- Xác định bất biến dữ liệu và bảo vệ chúng ngay trong câu lệnh SQL hoặc ràng buộc schema.
- Dùng cập nhật nguyên tử để tránh lỗi đọc rồi ghi khi có nhiều transaction.
- Chọn khóa bi quan hoặc optimistic locking theo mức độ tranh chấp.
- Thiết kế transaction ngắn, thứ tự lấy khóa nhất quán và ranh giới xử lý rõ ràng.
- Dùng idempotency key để chống thực hiện trùng khi client retry.
- Phân biệt lỗi có thể retry với lỗi nghiệp vụ và tình huống không biết `COMMIT` đã thành công hay chưa.
- Dùng transactional outbox khi transaction cần phát sinh sự kiện hoặc gọi dịch vụ bên ngoài.

Các ví dụ giả định MySQL 8.0 trở lên, bảng dùng InnoDB và ứng dụng kiểm tra dữ liệu đầu vào trước khi gửi SQL.

## 1. Bắt đầu từ bất biến dữ liệu

Bất biến là điều kiện phải luôn đúng sau mọi thao tác đã commit. Ví dụ:

- Tồn kho không được âm.
- Số dư tài khoản không được âm nếu nghiệp vụ không cho phép thấu chi.
- Một mã yêu cầu thanh toán chỉ được ghi nhận một lần.
- Một đơn hàng chỉ thuộc một khách hàng hợp lệ.
- Tổng tiền và trạng thái của một đơn hàng phải nhất quán với các dòng chi tiết.

Hãy xác định bất biến trước khi chọn cách khóa. Sau đó đặt bảo vệ gần dữ liệu nhất có thể: `NOT NULL`, `UNIQUE`, khóa ngoại, `CHECK` phù hợp và điều kiện trong `UPDATE`. Kiểm tra ở tầng ứng dụng vẫn cần thiết để trả thông báo dễ hiểu, nhưng không thể thay thế bảo vệ ở database vì hai request có thể cùng đọc một giá trị trước khi một trong hai kịp ghi.

Ví dụ, luồng đọc tồn kho rồi quyết định trừ hàng có lỗi tranh chấp:

```sql
SELECT available
FROM inventory
WHERE product_id = 10;
```

Nếu hai worker cùng đọc `available = 5`, cả hai có thể cùng kết luận rằng còn đủ hàng để xử lý đơn đặt 4 sản phẩm. Khi cả hai lần lượt ghi kết quả tính từ giá trị cũ, dữ liệu có thể sai. Vấn đề nằm ở khoảng thời gian giữa bước đọc và bước ghi.

## 2. Ưu tiên cập nhật nguyên tử khi nghiệp vụ cho phép

Nếu quy tắc có thể biểu diễn trong một câu lệnh, hãy đưa điều kiện kiểm tra vào chính câu `UPDATE`:

```sql
UPDATE inventory
SET available = available - 4,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 10
  AND available >= 4;
```

InnoDB thực hiện phép kiểm tra và thay đổi trên hàng dưới cơ chế khóa của câu lệnh. Hai transaction không thể cùng dùng một giá trị cũ để làm cho tồn kho âm. Ứng dụng kiểm tra số hàng bị ảnh hưởng ngay sau câu lệnh:

```sql
SELECT ROW_COUNT();
```

Nếu kết quả là `1`, hàng tồn kho đã được trừ. Nếu là `0`, sản phẩm không tồn tại hoặc không đủ hàng. Nếu cần phân biệt hai trường hợp, truy vấn thêm trong cùng transaction theo yêu cầu nghiệp vụ. Ví dụ này giả định lượng cần trừ là số dương; ứng dụng phải từ chối số lượng bằng 0 hoặc âm trước khi chạy SQL.

Khi việc trừ kho phải đi cùng ghi nhận đơn hàng, đặt cả hai thay đổi trong một transaction:

```sql
START TRANSACTION;

UPDATE inventory
SET available = available - 4,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 10
  AND available >= 4;

-- Ứng dụng kiểm tra ROW_COUNT() phải bằng 1.
-- Nếu bằng 0, ROLLBACK và trả kết quả hết hàng.

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (7001, 10, 4);

COMMIT;
```

Nếu thao tác `INSERT` thất bại, transaction phải `ROLLBACK` để hoàn lại số lượng đã trừ. Trong mã ứng dụng, nhánh kiểm tra số hàng bị ảnh hưởng và lệnh kết thúc transaction phải được thực hiện trên cùng một kết nối.

## 3. Khóa bi quan khi cần đọc rồi quyết định

Một số nghiệp vụ cần đọc nhiều cột hoặc nhiều hàng, tính toán rồi mới cập nhật. Khi quyết định phải dựa trên trạng thái hiện tại, có thể dùng `SELECT ... FOR UPDATE` trong transaction:

```sql
START TRANSACTION;

SELECT available, reorder_level
FROM inventory
WHERE product_id = 10
FOR UPDATE;

-- Ứng dụng kiểm tra điều kiện và tính số lượng cần đặt.
UPDATE inventory
SET available = available - 4
WHERE product_id = 10
  AND available >= 4;

COMMIT;
```

`FOR UPDATE` yêu cầu current read và giữ khóa ghi phù hợp đến khi transaction kết thúc. Transaction khác muốn thay đổi hàng đó phải chờ. Dùng khóa bi quan khi xung đột thường xuyên hoặc logic thực sự cần giữ trạng thái đã đọc trong suốt phần còn lại của transaction.

Các nguyên tắc khi dùng:

1. Dùng chỉ mục phù hợp để định vị chính xác hàng cần khóa. Truy vấn quét phạm vi rộng có thể giữ nhiều khóa hơn dự kiến.
2. Mở transaction ngay trước khi lấy khóa và kết thúc ngay sau khi hoàn tất thay đổi.
3. Không chờ người dùng, gọi HTTP, gửi email hoặc thực hiện công việc chậm khi đang giữ khóa.
4. Nếu phải khóa nhiều hàng, lấy khóa theo một thứ tự ổn định, chẳng hạn tăng dần theo khóa chính.
5. Kiểm tra số hàng bị ảnh hưởng và rollback khi một bước nghiệp vụ không đạt điều kiện.

### Ví dụ chuyển tiền giữa hai tài khoản

Giả sử cần chuyển 100 đơn vị từ tài khoản 100 sang tài khoản 200. Mọi luồng chuyển tiền phải khóa các tài khoản theo thứ tự `account_id` tăng dần, bất kể chiều chuyển tiền, để giảm nguy cơ deadlock:

```sql
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 100
FOR UPDATE;

SELECT account_id, balance
FROM accounts
WHERE account_id = 200
FOR UPDATE;

-- Ứng dụng xác nhận cả hai tài khoản tồn tại và số dư nguồn đủ.
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 100
  AND balance >= 100;

-- Nếu ROW_COUNT() không bằng 1: ROLLBACK.
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 200;

-- Xác nhận ROW_COUNT() bằng 1 cho cả hai lần UPDATE.
-- Nếu không đạt, ROLLBACK thay vì ghi ledger.
-- Ghi thêm bản ghi ledger/transfer trong cùng transaction.
COMMIT;
```

Nếu chuyển theo chiều ngược lại, ứng dụng vẫn khóa tài khoản 100 trước rồi mới khóa tài khoản 200, sau đó mới áp dụng vai trò nguồn và đích. Thứ tự khóa thống nhất giúp hai transaction không khóa A rồi chờ B trong khi transaction khác khóa B rồi chờ A. Khóa đúng thứ tự giảm deadlock nhưng không loại bỏ hoàn toàn deadlock do các bảng, index hoặc luồng khác tham gia.

Trong hệ thống thật, cần ghi một bản ghi chuyển tiền có mã nghiệp vụ duy nhất, kiểm tra số tiền dương, kiểm tra tài khoản nguồn và đích khác nhau nếu quy tắc yêu cầu, và xác nhận cả hai lần cập nhật đều thành công trước `COMMIT`.

## 4. Optimistic locking bằng cột version

Khi xung đột ít và không muốn giữ khóa trong lúc người dùng chỉnh sửa dữ liệu, có thể dùng optimistic locking. Mỗi hàng có cột phiên bản:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
) ENGINE = InnoDB;
```

Khi đọc tài liệu, ứng dụng nhận cả `version`. Khi lưu, nó yêu cầu version vẫn bằng giá trị đã đọc:

```sql
UPDATE documents
SET title = 'Kế hoạch cập nhật',
    body = 'Nội dung mới',
    version = version + 1
WHERE document_id = 501
  AND version = 7;
```

Nếu `ROW_COUNT()` bằng `1`, cập nhật thành công và version mới là `8`. Nếu bằng `0`, hàng đã bị xóa hoặc một transaction khác đã cập nhật trước; ứng dụng cần tải lại dữ liệu và yêu cầu người dùng giải quyết xung đột hoặc áp dụng quy tắc hợp nhất. Không nên tự động ghi đè bằng dữ liệu cũ vì điều đó làm mất thay đổi của người khác.

Việc tăng `version` trong cùng câu lệnh giúp mỗi lần cập nhật thành công đều làm hàng thay đổi, nên số hàng bị ảnh hưởng có thể dùng để phát hiện xung đột. Không chỉ kiểm tra giá trị trả về từ câu `SELECT` trước đó; điều kiện `WHERE version = ?` mới là bước so sánh và ghi nguyên tử.

## 5. Dùng ràng buộc để chống race condition

Mẫu `SELECT` kiểm tra rồi `INSERT` thường không an toàn:

```sql
SELECT COUNT(*)
FROM users
WHERE email = 'lan@example.com';

-- Nếu chưa có thì INSERT.
```

Hai transaction có thể cùng thấy kết quả bằng 0 và cùng cố gắng chèn. Bảo vệ đúng là đặt unique constraint:

```sql
ALTER TABLE users
ADD CONSTRAINT uq_users_email UNIQUE (email);
```

Sau đó thực hiện `INSERT` và xử lý lỗi duplicate key (`1062`) như một kết quả nghiệp vụ đã được database phân xử. Nếu email không được phép trùng, unique constraint là nguồn bảo đảm cuối cùng kể cả khi có nhiều ứng dụng hoặc worker cùng ghi.

Các ràng buộc thường dùng:

- `PRIMARY KEY` và `UNIQUE` để bảo vệ định danh và tính duy nhất.
- `NOT NULL` để ngăn thiếu giá trị bắt buộc.
- `FOREIGN KEY` để bảo vệ quan hệ tham chiếu.
- `CHECK` để biểu diễn điều kiện trên một hàng; MySQL thực thi `CHECK` từ phiên bản 8.0.16.

Không dùng `INSERT IGNORE` một cách tùy tiện để che lỗi. Câu lệnh có thể bỏ qua hàng vi phạm và phát cảnh báo, khiến ứng dụng tưởng rằng toàn bộ thao tác đã thành công. Hãy phân biệt duplicate key được dự kiến với lỗi dữ liệu khác.

## 6. Idempotency key để chống thực hiện trùng

Một request có thể được gửi lại vì client timeout, người dùng bấm nút nhiều lần, proxy retry hoặc worker xử lý lại message. Nếu mỗi lần gửi đều tạo một giao dịch mới, nghiệp vụ như thanh toán, đặt hàng hoặc trừ điểm có thể bị thực hiện nhiều lần.

**Idempotency** nghĩa là nhiều lần nhận cùng một yêu cầu logic tạo ra cùng một kết quả nghiệp vụ như một lần xử lý. Một cách triển khai phổ biến là client gửi một khóa duy nhất cho mỗi thao tác logic; server lưu khóa đó cùng kết quả xử lý trong database.

Ví dụ bảng lưu yêu cầu:

```sql
CREATE TABLE idempotency_requests (
    request_key VARBINARY(100) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    request_status ENUM('PROCESSING', 'COMPLETED') NOT NULL,
    response_payload JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (request_key)
) ENGINE = InnoDB;
```

Khi nhận yêu cầu chuyển tiền, server bắt đầu transaction và cố gắng ghi nhận `request_key` trước khi thực hiện thay đổi:

```sql
START TRANSACTION;

INSERT INTO idempotency_requests
    (request_key, request_hash, request_status)
VALUES
    ('transfer-req-9f82', UNHEX(SHA2('{"from":100,"to":200,"amount":100}', 256)), 'PROCESSING');

-- Chỉ khi INSERT thành công mới thực hiện nghiệp vụ.
-- Khóa tài khoản theo thứ tự ổn định, kiểm tra số dư,
-- cập nhật hai tài khoản và ghi transfer ledger.

UPDATE idempotency_requests
SET request_status = 'COMPLETED',
    response_payload = JSON_OBJECT(
        'transfer_id', 88001,
        'status', 'COMPLETED'
    )
WHERE request_key = 'transfer-req-9f82';

COMMIT;
```

Đây là một transaction duy nhất: bản ghi idempotency, thay đổi số dư, ledger và kết quả phản hồi cùng commit hoặc cùng rollback. Một request đồng thời dùng lại cùng `request_key` sẽ đụng unique key; thao tác chèn có thể phải chờ transaction đầu tiên kết thúc. Nếu transaction đầu tiên commit, request sau nhận duplicate key và không được thực hiện nghiệp vụ lần nữa. Nếu transaction đầu rollback, request sau có thể chèn khóa và trở thành request thực hiện.

Khi gặp duplicate key:

1. Rollback transaction hiện tại.
2. Đọc bản ghi `idempotency_requests` trong transaction mới hoặc autocommit.
3. So sánh `request_hash` với nội dung yêu cầu hiện tại. Cùng key nhưng payload khác phải bị từ chối; không được trả kết quả của một thao tác khác.
4. Nếu trạng thái là `COMPLETED`, trả lại `response_payload` đã lưu.

Trong thiết kế trên, trạng thái `PROCESSING` chưa commit riêng nên client khác không nhìn thấy nó trong lúc nghiệp vụ đang chạy. Đây là chủ ý để các thay đổi database có tính nguyên tử. Nếu quy trình cần giữ trạng thái xử lý qua nhiều transaction hoặc gọi dịch vụ lâu, cần thiết kế lease, timeout, chủ sở hữu xử lý và quy tắc phục hồi riêng; không mở một transaction database trong suốt thời gian chờ dịch vụ ngoài.

Khóa idempotency phải được giữ đủ lâu để bao phủ khoảng thời gian client có thể retry. Chính sách dọn dẹp cần tính đến thời gian retry tối đa và yêu cầu kiểm toán. Không tái sử dụng khóa cho một thao tác logic khác.

`request_hash` nên được tính từ biểu diễn payload đã chuẩn hóa (canonical form), gồm các trường có ý nghĩa nghiệp vụ và thứ tự/định dạng ổn định. Không dùng chuỗi JSON tùy ý do client gửi trực tiếp nếu cùng một payload có thể được tuần tự hóa thành nhiều chuỗi khác nhau. Ví dụ SQL ở trên minh họa cách lưu SHA-256 dưới dạng nhị phân; trong ứng dụng thực tế, thường tính hash ở tầng dịch vụ rồi truyền giá trị 32 byte vào câu `INSERT`.

## 7. Retry đúng cách khi transaction thất bại

Không phải mọi lỗi đều nên retry. Trước hết, phân loại lỗi theo nguyên nhân:

| Lỗi | Ý nghĩa thường gặp | Cách xử lý |
|---|---|---|
| Deadlock, MySQL error `1213`, SQLSTATE `40001` | InnoDB chọn transaction làm nạn nhân và rollback transaction đó | Chạy lại toàn bộ đơn vị nghiệp vụ trong transaction mới nếu thao tác có thể retry an toàn |
| Lock wait timeout, error `1205` | Transaction chờ khóa quá thời gian cấu hình | Mặc định InnoDB rollback câu lệnh bị timeout; ứng dụng nên rollback toàn bộ transaction nghiệp vụ rồi mới cân nhắc retry |
| Duplicate key, error `1062` | Vi phạm unique constraint hoặc request idempotency đã tồn tại | Xử lý theo quy tắc nghiệp vụ; không retry mù quáng |
| Validation, cú pháp, quyền hoặc khóa ngoại không hợp lệ | Yêu cầu hoặc câu lệnh có lỗi cố định | Sửa dữ liệu/câu lệnh/quyền; retry không giải quyết được |
| Mất kết nối khi đang `COMMIT` | Client không biết server đã commit hay chưa | Tra cứu bằng idempotency key hoặc mã nghiệp vụ trước khi quyết định gửi lại |

### Retry toàn bộ transaction

Deadlock làm InnoDB rollback toàn bộ transaction được chọn làm nạn nhân. Với lock wait timeout, mặc định chỉ câu lệnh bị timeout được rollback, trừ khi cấu hình `innodb_rollback_on_timeout` thay đổi hành vi. Vì vậy, cách xử lý an toàn ở tầng ứng dụng là rollback toàn bộ transaction logic sau lỗi có thể retry, rồi bắt đầu transaction mới và đọc lại trạng thái.

Không chỉ chạy lại câu SQL cuối cùng. Những quyết định trước đó có thể dựa trên dữ liệu đã cũ hoặc các bước trước đã bị rollback. Hãy chạy lại từ đầu đơn vị nghiệp vụ có ranh giới transaction rõ ràng.

Luồng xử lý khái niệm:

```text
Bắt đầu transaction mới
        |
Thực hiện toàn bộ nghiệp vụ
        |
      COMMIT
        |
   Thành công? ---- Có ----> Trả kết quả
        |
       Không
        |
ROLLBACK (nếu kết nối còn dùng được)
        |
Lỗi có thể retry và còn lượt?
        | Có                 | Không
        v                    v
Chờ backoff + jitter     Trả lỗi/đưa xử lý tiếp
        |
Quay lại transaction mới
```

Backoff theo cấp số nhân kết hợp jitter giúp các worker không đồng loạt retry ngay cùng lúc:

```text
delay = min(max_delay, base_delay * 2^(attempt - 1))
sleep(random(0, delay))
```

Giới hạn số lần retry và tổng thời gian xử lý. Thực hiện thời gian chờ sau khi transaction cũ đã kết thúc để không tiếp tục giữ khóa trong lúc ngủ. Nếu đã hết thời hạn request, trả trạng thái có thể thử lại sau hoặc chuyển công việc sang hàng đợi phù hợp.

### Mất kết nối đúng lúc COMMIT

Đây là trường hợp đặc biệt. Server có thể đã ghi commit thành công nhưng phản hồi chưa tới client; hoặc server chưa commit. Client chỉ biết kết nối bị mất, không biết kết quả cuối cùng. Gửi lại một câu `UPDATE balance = balance - 100` không có idempotency có thể trừ tiền lần thứ hai.

Khi có idempotency key, client gửi lại cùng key và payload. Server kiểm tra bảng idempotency: nếu thao tác trước đã commit, trả kết quả đã lưu; nếu chưa commit, request có thể được xử lý. Nếu không có khóa idempotency hoặc mã nghiệp vụ duy nhất, cần tra cứu trạng thái bằng một định danh nghiệp vụ trước khi quyết định retry.

## 8. Transaction không bao trùm dịch vụ bên ngoài

Transaction InnoDB chỉ điều khiển thay đổi trong database tham gia transaction. Nó không thể rollback một email đã gửi, một lời gọi API đã được dịch vụ khác chấp nhận hoặc một khoản thanh toán đã hoàn tất ở cổng thanh toán.

Không nên giữ transaction và khóa hàng trong lúc gọi dịch vụ bên ngoài. Một mẫu phổ biến là **transactional outbox**:

1. Trong cùng transaction, cập nhật dữ liệu nghiệp vụ và chèn một sự kiện vào bảng `outbox`.
2. Commit transaction. Nếu transaction rollback, cả thay đổi nghiệp vụ và sự kiện đều không tồn tại.
3. Một worker riêng đọc các sự kiện chưa gửi, gửi tới broker hoặc dịch vụ đích, rồi đánh dấu đã gửi.
4. Consumer xử lý sự kiện theo `event_id` duy nhất để chống tác động trùng khi worker gửi lại sau timeout.

Outbox thường cung cấp giao nhận ít nhất một lần (at-least-once), vì worker có thể gửi thành công rồi mất kết nối trước khi đánh dấu đã gửi. Consumer cần idempotent hoặc có bảng deduplication. Không nên hứa hẹn “exactly once” xuyên qua nhiều hệ thống chỉ bằng một transaction MySQL.

Nếu gọi cổng thanh toán, hãy dùng idempotency key do nghiệp vụ tạo và gửi cùng mỗi lần retry tới cổng thanh toán, nếu dịch vụ hỗ trợ. Database và cổng thanh toán cần cùng một mã tham chiếu để đối soát trạng thái khi kết quả mạng không rõ ràng.

## 9. Checklist thiết kế thao tác đồng thời

Trước khi triển khai một thao tác ghi quan trọng, hãy trả lời:

- Bất biến nào phải luôn đúng sau commit?
- Có thể biểu diễn điều kiện và thay đổi trong một câu `UPDATE` nguyên tử không?
- Nếu cần nhiều bước, transaction có bao trùm tất cả thay đổi database liên quan không?
- Có cần `FOR UPDATE`, hay optimistic locking bằng version là đủ?
- Các transaction có lấy khóa theo cùng thứ tự không?
- Có unique constraint để ngăn bản ghi trùng ở cấp database không?
- Request có idempotency key hoặc mã nghiệp vụ duy nhất không?
- Lỗi deadlock, timeout, duplicate key và mất kết nối lúc commit được phân loại riêng chưa?
- Retry có chạy lại toàn bộ transaction, có giới hạn lượt và backoff không?
- Email, HTTP, broker hoặc thanh toán có được tách khỏi transaction bằng outbox hoặc cơ chế idempotent không?

## 10. Bài thực hành

Giả sử có các bảng `inventory(product_id, available)`, `accounts(account_id, balance)` và `documents(document_id, title, body, version)`.

1. Viết một câu `UPDATE` trừ 3 sản phẩm khỏi tồn kho chỉ khi `available >= 3`. Nêu cách ứng dụng xác định thành công hay hết hàng.
2. Mở hai session cùng đặt mua số lượng 4 khi tồn kho là 5. Thực hiện cập nhật nguyên tử ở cả hai session và quan sát kết quả.
3. Viết thao tác chuyển 100 đơn vị giữa hai tài khoản, khóa hai hàng theo thứ tự `account_id` tăng dần và ghi ledger trong cùng transaction.
4. Viết câu `UPDATE` optimistic locking cho tài liệu có `version = 12`. Mô tả cách xử lý khi số hàng bị ảnh hưởng bằng 0.
5. Thiết kế unique key cho `request_key`. Mô phỏng hai request đồng thời dùng cùng key và xác định request nào được phép thực hiện nghiệp vụ.
6. Phân loại deadlock, lock wait timeout, duplicate key và mất kết nối ngay sau `COMMIT`. Với mỗi trường hợp, nêu rõ có retry hay không và cần bắt đầu lại từ đâu.
7. Phác thảo bảng outbox và quy tắc để consumer xử lý cùng `event_id` nhiều lần mà không lặp tác động nghiệp vụ.

## Ghi nhớ

- Bảo vệ bất biến bằng câu lệnh nguyên tử và ràng buộc database; không dựa vào mẫu đọc rồi ghi tách rời.
- Dùng khóa bi quan khi cần giữ trạng thái hiện tại trong transaction; dùng version khi muốn phát hiện ghi đè cạnh tranh.
- Giữ transaction ngắn, dùng index phù hợp và lấy nhiều khóa theo thứ tự ổn định.
- Idempotency key giúp request retry không thực hiện cùng nghiệp vụ hai lần; cùng key phải gắn với cùng payload.
- Sau deadlock hoặc timeout, rollback đơn vị nghiệp vụ và retry toàn bộ transaction trong phiên mới khi lỗi có thể retry.
- Mất kết nối lúc `COMMIT` tạo kết quả chưa rõ; hãy tra cứu bằng idempotency key trước khi thực hiện lại.
- Tách tác động bên ngoài khỏi transaction bằng outbox và làm consumer idempotent.
